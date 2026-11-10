# postman DOX

## Purpose

- Runnable Postman contract for every Octo HTTP endpoint, importable into the Postman app or run with the Postman CLI

## Ownership

- `collections/Octo/` — v3 YAML collection (one `*.request.yaml` per request, collection/folder metadata in `.resources/definition.yaml`): `Auth` (`POST /auth/token`, `GET /auth/users/me/`), `Health`, `Posts` (`POST /save`, `POST /process/all`, `GET /posts/{post_id}`, `GET /search` with every `PointFilter` param present but disabled), `Tasks` (`GET /api/tasks`, `GET /api/tasks/{task_id}`, `POST /api/tasks/{task_id}/retry`)
- `environments/Octo Local.environment.yaml` — `base_url`, `username`/`password` (defaults match `cli.postgres`: `admin@octo.local`/`admin`), and script-managed `access_token`, `access_token_expires_at` (ms epoch), `post_id`, `log_id`, `task_id`

## Local Contracts

- Auth lives at collection level: Bearer `{{access_token}}`, inherited by every request; only `Login` and `Health` set `noauth`
- The collection pre-request script logs in via `pm.sendRequest` to `/auth/token` when `access_token` is missing or expires within `token_refresh_skew_seconds` (collection var, default 30), reading `exp` from the JWT. The API has no refresh-token endpoint, so refresh means re-login
- The collection test script clears `access_token` on any 401 so the next request re-logs in; the failing request itself is not retried
- New endpoints get a request here in the matching folder, with `pm.test` assertions on status and shape; chain ids through environment variables, never hardcode them
- `password` and `access_token` are `secret` type; never commit a real token or non-default credentials

## Work Guidance

- `POST /process/all` claims every `PENDING` post of the user and starts the real pipeline; running the whole collection has that side effect. `Retry task` re-runs the failed posts of `task_id` the same way

## Verification

- With the API up: `postman collection lint postman/collections/Octo`, then `postman collection run postman/collections/Octo -e "postman/environments/Octo Local.environment.yaml" [--env-var base_url=http://localhost:8123] [-i "<request or folder>"]`

## Child DOX Index

- None
