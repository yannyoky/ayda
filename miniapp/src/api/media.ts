import { api, unwrap } from './client'

export const MAX_PHOTO_BYTES = 10 * 1024 * 1024
export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/heic', 'image/webp'] as const
export type PhotoType = (typeof PHOTO_TYPES)[number]

/** Content type of a picked photo; some browsers leave `type` empty for HEIC. */
export function photoType(file: File): PhotoType | null {
  const declared = file.type.toLowerCase()
  if ((PHOTO_TYPES as readonly string[]).includes(declared)) return declared as PhotoType
  if (declared === 'image/heif' || /\.(heic|heif)$/i.test(file.name)) return 'image/heic'
  if (/\.jpe?g$/i.test(file.name)) return 'image/jpeg'
  return null
}

/** US-10: get a presigned slot and PUT the file straight to storage. Returns the media id. */
export async function uploadPhoto(file: File): Promise<string> {
  const contentType = photoType(file)
  if (!contentType) throw new Error('unsupported photo type')
  const slot = await unwrap(api.POST('/media/uploads', { body: { content_type: contentType, size_bytes: file.size } }))
  const response = await fetch(slot.upload_url, { method: 'PUT', headers: slot.headers, body: file })
  if (!response.ok) throw new Error(`upload failed: ${response.status}`)
  return slot.media_id
}
