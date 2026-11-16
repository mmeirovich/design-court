resource "stratus_bucket" "user_media" {
  name       = "pn-user-media"
  versioning = false

  cors_rule {
    allowed_origins = ["https://app.pixelnest.example"]
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_headers = ["content-type"]
    max_age_seconds = 3600
  }
}

resource "stratus_function" "avatar_thumbnailer" {
  name                 = "avatar-thumbnailer"
  runtime              = "python3.12"
  handler              = "src.avatars.thumbnail.handler"
  memory_mb            = 512
  timeout_seconds      = 30
  reserved_concurrency = 6
}

resource "stratus_bucket_notification" "avatar_created" {
  bucket        = stratus_bucket.user_media.name
  events        = ["object_created"]
  filter_prefix = "avatars/"
  target        = stratus_function.avatar_thumbnailer.arn
}
