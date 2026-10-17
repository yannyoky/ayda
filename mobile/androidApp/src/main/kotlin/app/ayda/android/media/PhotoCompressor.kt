package app.ayda.android.media

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayOutputStream
import kotlin.math.max

/**
 * Turns a picked or shot photo into a small JPEG for a proof.
 *
 * The photo is decoded, turned upright, scaled to at most [MAX_SIDE] px and encoded again.
 * Re-encoding writes no EXIF at all, so the location and the camera details stay on the phone.
 */
object PhotoCompressor {
    const val MAX_SIDE = 2048
    const val QUALITY = 85

    /** Returns null when the file can't be read as an image. */
    fun compress(
        resolver: ContentResolver,
        uri: Uri,
    ): ByteArray? =
        runCatching {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            resolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            val longest = max(bounds.outWidth, bounds.outHeight)
            if (longest <= 0) return null

            var sample = 1
            while (longest / (sample * 2) >= MAX_SIDE) sample *= 2
            val decoded =
                resolver.openInputStream(uri)?.use {
                    BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
                } ?: return null
            val degrees = resolver.openInputStream(uri)?.use { ExifInterface(it).rotationDegrees } ?: 0
            encode(upright(decoded, degrees))
        }.getOrNull()

    fun encode(bitmap: Bitmap): ByteArray =
        ByteArrayOutputStream().use { out ->
            bitmap.compress(Bitmap.CompressFormat.JPEG, QUALITY, out)
            out.toByteArray()
        }

    /** Scales the longest side down to [MAX_SIDE] and applies the EXIF rotation. */
    fun upright(
        bitmap: Bitmap,
        degrees: Int,
    ): Bitmap {
        val scale = MAX_SIDE.toFloat() / max(bitmap.width, bitmap.height)
        if (degrees == 0 && scale >= 1f) return bitmap
        val matrix =
            Matrix().apply {
                if (scale < 1f) postScale(scale, scale)
                postRotate(degrees.toFloat())
            }
        val result = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        if (result != bitmap) bitmap.recycle()
        return result
    }
}
