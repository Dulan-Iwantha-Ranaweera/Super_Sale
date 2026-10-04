/**
 * Client-side avatar preparation.
 *
 * The photo is stored inline on the user document, so the browser does the
 * resizing: a phone snapshot is cropped square and scaled to 256px before it
 * ever leaves the page. That keeps the upload tens of kilobytes instead of
 * several megabytes, and means the app needs no file storage at all.
 */

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024
export const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const OUTPUT_SIZE = 256
const OUTPUT_QUALITY = 0.86

export function describeFileError(file) {
  if (!file) return 'Choose an image file'
  if (!ACCEPTED_TYPES.includes(file.type)) return 'Photo must be a PNG, JPEG or WebP image'
  if (file.size > MAX_UPLOAD_BYTES) return 'Photo must be smaller than 8 MB'
  return null
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('That file could not be read as an image'))
    }
    image.src = url
  })
}

/** Centre-crop to a square, scale to 256px, and return a JPEG data URL. */
export async function fileToAvatarDataUrl(file) {
  const problem = describeFileError(file)
  if (problem) throw new Error(problem)

  const image = await loadImage(file)
  const side = Math.min(image.naturalWidth, image.naturalHeight)
  if (!side) throw new Error('That image appears to be empty')

  const sourceX = (image.naturalWidth - side) / 2
  const sourceY = (image.naturalHeight - side) / 2

  const canvas = document.createElement('canvas')
  canvas.width = OUTPUT_SIZE
  canvas.height = OUTPUT_SIZE
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Your browser could not process the image')

  // JPEG has no alpha, so fill first or transparent PNGs come out black.
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, OUTPUT_SIZE, OUTPUT_SIZE)
  context.drawImage(image, sourceX, sourceY, side, side, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE)

  return canvas.toDataURL('image/jpeg', OUTPUT_QUALITY)
}
