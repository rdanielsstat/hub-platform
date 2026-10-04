/**
 * Input length limits, mirroring the API's (backend/app/models/; also in
 * openapi.yaml). Used as `maxLength` on form fields so a user can't type
 * past a limit and only find out on save. The API still validates; these
 * are a convenience, not the enforcement.
 *
 * `maxLength` counts UTF-16 code units and the API counts characters, so
 * an emoji (two units) uses up the browser's limit faster: the browser can
 * stop slightly early, never late.
 */

/** RFC 5321's 254-character maximum, which the API's email check applies. */
export const EMAIL_MAX_LENGTH = 254
export const PASSWORD_MAX_LENGTH = 256
export const DISPLAY_NAME_MAX_LENGTH = 100

export const PROJECT_NAME_MAX_LENGTH = 256
export const PITCH_MAX_LENGTH = 2000
export const DESCRIPTION_MAX_LENGTH = 5000
export const NEXT_ACTION_MAX_LENGTH = 1000
export const NOTE_MAX_LENGTH = 10000

export const TAG_MAX_LENGTH = 64
export const TAGS_MAX_ITEMS = 50
/**
 * Quick capture takes tags as one comma-separated field, so per-tag length
 * can't be a `maxLength`; this caps the field at room for the maximum
 * number of full-length tags with separators. A single over-long tag in it
 * is still refused by the API (422, shown as a toast).
 */
export const TAG_LIST_INPUT_MAX_LENGTH = TAGS_MAX_ITEMS * (TAG_MAX_LENGTH + 2)

export const LINK_URL_MAX_LENGTH = 2048
export const LINK_LABEL_MAX_LENGTH = 200
