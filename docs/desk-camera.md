# Desk camera (MediaMTX)

An old iPhone publishes its camera from Safari to MediaMTX on home-media.
Browsers watch it through Caddy behind Authelia. The service is
`roles/docker/deploy-docker-swarm/templates/compose/mediamtx.yml.j2`.

Placeholders below: `<domain>` is `public_top_domain` and `<media_ip>` is
`media_ip`, both in `vars/docker_swarm.sops.yml`. Passwords live there too.
Read one with:

```bash
sops -d --extract '["mediamtx_obs_pass"]' vars/docker_swarm.sops.yml
```

## Publish from the phone

1. Safari on the home Wi-Fi: `https://cam-home.<domain>/desk/publish`, log in to Authelia.
2. Video device: Back Camera. Codec: **H264** (Home Assistant can't play VP9,
   and the iPhone encodes VP9 in software). Audio device: none.
3. Tap publish. Keep Safari open with Auto-Lock set to Never; Guided Access
   keeps the phone on the page.

## Watch

| Client | Address | Login |
|---|---|---|
| Any browser | `https://cam-home.<domain>/desk/` | Authelia |
| Home Assistant | Generic Camera, `rtsp://<media_ip>:8554/desk`, TCP | none, allowed by IP |
| OBS / VLC on the LAN | `rtsp://obs:<mediamtx_obs_pass>@<media_ip>:8554/desk` | `obs` user |

Video always flows directly to home-media on UDP 8189, so watching from
outside the house needs the WireGuard VPN.

### OBS

Add a **Media Source**, untick "Local File", set the input to the `obs` RTSP
address above and leave "Input format" empty. The `obs` user can only read
streams, never publish or change settings.

A Browser Source pointed at `https://cam-home.<domain>/desk/` also works with
no password, after logging in to Authelia through "Interact", but it shows the
web player and the login expires.

## Access rules

- Anonymous publish and read are allowed only from the swarm overlay (Caddy,
  so Authelia) and home-edge (Home Assistant). Any other LAN device gets 401
  unless it uses the `obs` user.
- MediaMTX passwords may only contain `A-Z a-z 0-9 ! $ ( ) * + . ; < = > [ ] ^ _ - , @ # &`.
  The generated ones are 32 letters and digits.

## Record

Off by default. Turn it on and off through the API with the `admin` user:

```bash
curl -u "admin:$(sops -d --extract '["mediamtx_api_pass"]' vars/docker_swarm.sops.yml)" \
  -X PATCH http://<media_ip>:9997/v3/config/paths/patch/desk -d '{"record": true}'
```

Send `{"record": false}` to stop. Segments land in
`/mnt/storage/Media/Recordings/desk/` as 10 minute MP4 files and are never
deleted automatically. A restart of the container turns recording off again.

## Who is connected

```bash
curl -u admin:<mediamtx_api_pass> http://<media_ip>:9997/v3/webrtcsessions/list   # browser publishers and viewers
curl -u admin:<mediamtx_api_pass> http://<media_ip>:9997/v3/rtspsessions/list     # Home Assistant, OBS, VLC
```
