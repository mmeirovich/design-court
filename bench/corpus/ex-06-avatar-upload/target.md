# ADR-014: Direct-to-storage avatar uploads

| | |
|---|---|
| Status | Proposed |
| Authors | Priya N. (profiles), Tomas W. (platform) |
| Reviewers | Platform, security champion |
| Touches | `src/avatars/presign.py`, `src/avatars/thumbnail.py`, `infra/storage.tf`, `infra/cdn.yaml` |
| Vendor reference | `docs/object-storage.md` |

## Context

Profiles show a generated initials badge today. In the last two beta surveys real avatars were
the most requested profile feature (31% of free-text answers), and we want them in place before
the March campaign.

The obvious implementation, posting the image to `app-api` and letting it write to storage,
does not fit the fleet. `app-api` runs 8 pods with 2 workers each, 16 workers in total. A 5 MB
image on a mobile connection holds a worker for about 10 s (p99 12 s in the beta transfer
logs). At the launch rate we expect (see Expected load) that is roughly 9 uploads/s x 10 s =
90 workers busy with uploads alone, against 16 available. The bytes have to bypass `app-api`.

## Decision

Browsers upload straight to object storage with a presigned PUT URL. A storage-triggered
function builds thumbnails. The existing edge distribution serves everything. `app-api` only
issues URLs and records which object is the user's current avatar.

### Upload flow

1. The user chooses a file. The client reads `file.name`, `file.type` and `file.size`, and
   rejects anything over 5 MB locally.
2. On Save, the client calls `POST /api/avatar/upload-url` with `{filename, contentType, size}`.
   The endpoint requires a signed-in session, accepts any `image/*` content type and a declared
   size of up to 5 MB (413 otherwise), and returns `{uploadUrl, key}`.
3. The client PUTs the file to `uploadUrl` with the Content-Type it declared.
4. The client calls `POST /api/avatar/confirm` with the `key`. The server checks that the
   object exists and stores the key on the user's row.
5. The UI polls for the 512 px thumbnail (up to 10 tries, 1 s apart) and swaps it in. If the
   thumbnailer could not decode the file, the user keeps the initials badge and sees "We
   couldn't process that image".

The URL expires 60 seconds after it is issued. The client asks for it when the user presses
Save, not when they pick the file, and the PUT starts immediately; the beta p99 of 12 s for a
5 MB file leaves a wide margin. Storage checks expiry when the request arrives, so a transfer
that began in time is not cut off.

We accept any `image/*` type rather than keeping an allowlist because the formats users bring
keep changing (HEIC, AVIF) and we would rather not ship a release for each one. The
thumbnailer is the practical filter: whatever Pillow can decode gets a thumbnail.

### Object layout

| Object | Key | Written by |
|---|---|---|
| Original | `avatars/orig/<filename>` | browser, via presigned PUT |
| 128 px thumbnail | `avatars/thumb/128/<filename>` | thumbnailer |
| 512 px thumbnail | `avatars/thumb/512/<filename>` | thumbnailer |

`<filename>` is the name of the file the user chose, lower-cased, with path separators and
unusual characters replaced (`safe_name`). Keeping the original name makes keys readable in
support tooling and gives users a sensible name when they download their original from
settings.

### Thumbnails

Storage emits an object-created notification for each new original, and `avatar-thumbnailer`
turns it into two square JPEG thumbnails (centre crop, quality 85). The function runs with
512 MB of memory and a 30 s timeout. One invocation, including downloading the original and
uploading both thumbnails, takes about 1.2 s in staging.

### Serving

Avatars are served from `https://app.pixelnest.example/avatars/*` by the existing edge
distribution (`infra/cdn.yaml`), not from a separate media domain. That keeps the URLs
first-party, needs no new DNS or certificates, and the `img-src 'self'` policy we already send
keeps working. The edge serves each object with the Content-Type it was stored with and caches
it for 24 hours.

### Replacing and removing avatars

When the user confirms a new avatar, the server deletes their previous original and both
previous thumbnails, then points the profile row at the new key. The user sees the new image
straight away because the UI re-renders from the key returned by confirm. Deleting an account
removes the avatar objects along with the rest of the user's data.

Avatars are visible to other users as soon as the thumbnails exist. Inappropriate images are
handled through the existing abuse-report flow, and reported avatars are removed by the T&S
team.

## Expected load

| Quantity | Value | Basis |
|---|---|---|
| Steady state | ~2,000 avatar changes/day | beta rate scaled to 310k weekly actives |
| Launch email | 54,000 recipients | marketing plan |
| Launch peak | ~5,400 uploads in 10 min, ~9/s | 10% of recipients act in the first 10 min (last campaign) |
| Original size | avg 1.8 MB, max 5 MB | beta uploads |
| Storage added at peak | ~9.7 GB of originals | 5,400 x 1.8 MB |
| Thumbnailer | 6 reserved executions, ~1.2 s each | `infra/storage.tf`, staging timing |

With 6 reserved executions at about 1.2 s per invocation the thumbnailer has comfortable
headroom over 9 uploads/s, so we do not expect a backlog at launch and the 10 s the UI waits
for a thumbnail should be enough. Steady-state load is negligible.

## Consequences

- Upload bandwidth and connection time move off `app-api`; its worker count no longer scales
  with avatar traffic.
- Avatar URLs are stable and cacheable, and the edge absorbs reads.
- The key stored on the user row is the only link between a user and their objects, so
  `confirm` must be the only code path that writes it.
- Two moving parts are new: the notification rule and the thumbnailer. Both are in
  `infra/storage.tf` and covered by the existing Terraform review.
- Originals are kept at full size (up to 5 MB each). At 310k weekly actives, if every active
  user set one, that is under 600 GB, which we accept.

## Alternatives considered

- **Proxy the upload through `app-api`.** Rejected on worker arithmetic (see Context). Raising
  the worker count to cover launch day would mean paying for pods that sit idle the rest of
  the year.
- **A separate media domain.** Rejected for now: a second origin means new DNS and TLS, a
  second CSP and CORS configuration, and cookie scoping work, all for a feature that launches
  in March.
- **Resize in the browser before uploading.** This would cut a typical upload from 1.8 MB to
  about 200 KB. We still need server-side thumbnails for older clients and cannot trust what a
  browser sends, so it is an optimisation to add later rather than an alternative.
- **A hosted image service.** The quote was $1,900/month against roughly $40/month for the
  function and storage at our volume.

## Rollout

1. Ship behind the `avatar_upload` flag, staff-only, for one week. Watch thumbnailer error
   rate and the 413/400 rates on `/api/avatar/upload-url`.
2. Enable for everyone on the day of the launch email.
3. Rollback is disabling the flag. Existing objects stay where they are, and users fall back to
   the initials badge.

## Open questions

- Animated GIFs: the thumbnailer keeps the first frame. Is that acceptable for launch?
- Should avatars appear in notification emails? Not in scope here, but the stable URLs make it
  easy to add.
- Do we want a per-user daily cap on avatar changes? Beta usage suggests it is not needed.
