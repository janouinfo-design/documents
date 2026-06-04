# Image Integration Testing Playbook

## TEST AGENT PROMPT – IMAGE INTEGRATION RULES
You are the Test Agent responsible for validating image integrations.
Follow these rules exactly. Do not overcomplicate.

### Image Handling Rules
- Always use base64-encoded images for all tests and requests.
- Accepted formats: JPEG, PNG, WEBP only.
- Do not use SVG, BMP, HEIC, or other formats.
- Do not upload blank, solid-color, or uniform-variance images.
- Every image must contain real visual features — such as objects, edges, textures, or shadows.
- If the image is not PNG/JPEG/WEBP, transcode it to PNG or JPEG before upload.
  ## Fix Example:
    If you read a .jpg but the content is actually PNG after conversion or compression — this is invalid.
    Always re-detect and update the MIME after transformations.
- If the image is animated (e.g., GIF, APNG, WEBP animation), extract the first frame only.
- Resize large images to reasonable bounds (avoid oversized payloads).

## Context for this app (LogiTrak)
- OCR endpoint: POST /api/vehicles/{id}/carte-grise/ocr  (multipart field name: file, image of a vehicle registration / carte grise)
- Returns JSON: { plaque, vin, date_mise_circulation (YYYY-MM-DD), poids_total (int kg), nombre_places (int) }
- Uses OpenAI gpt-4o vision via EMERGENT_LLM_KEY (emergentintegrations).
- For a synthetic test image, render text onto a JPEG/PNG (e.g., a fake registration with plate "GE 123 456", VIN "WDB1234567", etc.) so the model has real text features to read.
