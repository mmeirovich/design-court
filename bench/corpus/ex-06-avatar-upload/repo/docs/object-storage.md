# Stratus Object Storage: client reference

Internal mirror of the parts of the vendor reference we rely on ("Browser uploads" and
"Event notifications"). Last synced 2026-08.

## Presigned PUT URLs

`presign_put(bucket, key, content_type=None, expires_in=900)` returns a URL that permits a
single-object PUT to `key`.

- The signature covers the method, bucket, key and expiry. If `content_type` is passed it is
  signed as well, and the PUT must send the same `Content-Type` header.
- `expires_in` is in seconds, from 1 to 604800. Expiry is evaluated when storage receives the
  request; a transfer that has already started is allowed to finish.
- The request body size is not part of the signature. A presigned PUT accepts a body of any
  size up to the single-request maximum of 5 GB, whatever size the caller declared when it
  asked for the URL.
- A URL can be used any number of times until it expires. Each PUT overwrites the object.

## Presigned POST policies

`presign_post(bucket, key, conditions, expires_in)` returns a form action and a set of fields
for a multipart/form-data POST. Storage evaluates the policy conditions itself:

- `["content-length-range", min, max]` bounds the size of the uploaded file in bytes.
- `["eq", "$Content-Type", "image/webp"]` and `["starts-with", "$Content-Type", "image/"]`
  constrain the declared content type.

A request that violates a condition is rejected with 403 before any bytes are stored.

## Event notifications

- A notification rule names one or more events (`object_created`, `object_removed`), an
  optional key `filter_prefix` and `filter_suffix`, and a target function.
- `object_created` fires for every successful PUT, POST or copy, including a PUT that
  overwrites an existing key.
- Delivery is at least once. The same event can be delivered more than once, and events for
  different objects are not ordered.
- A rule matches on the key of the object only.
- A failing function invocation is retried up to 2 times, one minute apart.
