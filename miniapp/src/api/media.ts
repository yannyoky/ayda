import { api, unwrap, type Schemas } from './client'

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

type RecordingType = Schemas['ChatUploadInput']['content_type']
const RECORDING_TYPES: Record<Schemas['ChatUploadInput']['kind'], readonly RecordingType[]> = {
  voice: ['audio/webm', 'audio/ogg', 'audio/mp4', 'audio/aac', 'audio/mpeg'],
  video_note: ['video/webm', 'video/mp4', 'video/quicktime'],
}

/** The contract's type for a recording: MediaRecorder adds codecs (`audio/webm;codecs=opus`). */
export function recordingType(kind: Schemas['ChatUploadInput']['kind'], blob: Blob): RecordingType | null {
  const base = blob.type.split(';')[0]!.trim().toLowerCase()
  return (RECORDING_TYPES[kind] as readonly string[]).includes(base) ? (base as RecordingType) : null
}

/** ADR 0019: a presigned slot in the chat, then a PUT straight to storage. Returns the id
 *  to send as `attachment_id`; the server re-encodes the recording before anyone plays it. */
export async function uploadRecording(conversationId: string, kind: Schemas['ChatUploadInput']['kind'], blob: Blob): Promise<string> {
  const contentType = recordingType(kind, blob)
  if (!contentType) throw new Error('unsupported recording type')
  const slot = await unwrap(
    api.POST('/conversations/{conversation_id}/uploads', {
      params: { path: { conversation_id: conversationId } },
      body: { kind, content_type: contentType, size_bytes: blob.size },
    }),
  )
  const response = await fetch(slot.upload_url, { method: 'PUT', headers: slot.headers, body: blob })
  if (!response.ok) throw new Error(`upload failed: ${response.status}`)
  return slot.media_id
}
