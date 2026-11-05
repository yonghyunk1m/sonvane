# Hugging Face preview

Status (2026-11-04): the Protected Docker Space [yonghyunk1m/sonvane](https://huggingface.co/spaces/yonghyunk1m/sonvane) runs a proxy to the existing server GPU. The app is accessible anonymously at its direct `.hf.space` URL; the Space source remains private. No Hugging Face GPU rental was provisioned.

## Runtime

The Space serves Overview and Studio through one host. Its root redirects to `/demo/`, preserving relative CSS and JavaScript URLs. A static copy cannot execute the planning, generation, evaluation or export APIs.

`deploy/huggingface/` contains the Docker proxy. Set `SONVANE_BACKEND_URL` and `SONVANE_RELAY_TOKEN` as **Space Secrets**, and `SONVANE_PUBLIC_ORIGIN` as a Space variable. Never put the backend address or credentials in source, browser JavaScript, release notes or images. The Docker build includes `VERSION`; `/healthz` reports it without returning connection details.

`deploy/gateway.py` runs beside the application core. It requires the relay credential and forwards only permitted application routes and assets. Configure its `SONVANE_CORE_URL`, `SONVANE_RELAY_TOKEN` and `SONVANE_DEMO_DATA` in the server environment. Keep its listening socket private; expose only the authenticated relay through the configured connection. Core model credentials stay on the GPU server.

The demo has a separate empty data directory. Signed, secure browser cookies map to server-side ownership records for profiles and projects. Another visitor cannot access a project's media or actions. Requests are bounded to 32 MB, with three projects per visitor, forty projects overall and mutation rate limits. The current hosted upload ceiling is lower than the local application's 250 MB ceiling. Model-request budgets are also configured on the server.

## Verified

- Hosted upload of an original six-second synthetic test video.
- One real Muse sound plan, approval of its saved revision, three generated music candidates and rendered video output.
- Rejection of another visitor's access to the generated project.
- Regression tests for root redirection, server credential handling, cross-origin writes and private error responses.

The fixture verifies the workflow, not creative quality. Browser checks and generated media are stored in ignored local verification artifacts, not in the public repository.

## Operations and remaining limits

For Studio, the GPU server, application core, relay and external connection must stay running. A changed connection address must be updated in Space Secrets. Current process state and connection details are kept in private server configuration, not in this document. This is a preview connection, not a managed high-availability deployment.

Automatic expiry of uploaded media is not implemented. Clear demo data deliberately according to the operator's retention policy. The Space is Protected and the GitHub repository remains private. Publication of the GitHub source requires separate owner authorization.

For every application update, follow [the versioning workflow](versioning.md), deploy matching source and proxy versions, and verify the browser—not just the container build. Official hosting reference: [Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker).

## Final demo film

The deployment packages the approved final MP4, poster, player HTML/CSS/JavaScript and font in `deploy/huggingface/media/`. These deployment-only copies are ignored by Git; `.gitkeep` preserves a buildable empty directory for source checkouts. Copy the player files from `app/static/demo/` and the font with its license from `app/static/assets/` when preparing a deployment.

The Space serves only the explicitly listed film assets through `FileResponse`, supporting byte-range requests and seeking. The film plays without a connection to the GPU backend. If a packaged file is absent, the route falls back to the existing proxy. The local source checkout does not include the final MP4.
