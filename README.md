# Seadrop - Simplifying file transfers

Seadrop is a website allowing users to send files to all other users in a given session. Once downloaded, files will disappear from the server.

# Current architecture

## Pages

### Frontend

#### `[GET] /`
Landing page, allows users to join sessions.

#### `[GET] /s/<session>`
Session page, allows users to upload and download files.

### Backend

#### `[POST] /upload/<session>`
Endpoint for uploading files to a session.
Upload a single file as `file`.

#### `[GET] /download/<session>/<file>`
Endpoint for downloading a file.
Will delete file once downloaded.

## Websocket Details

Websockets are used to communicate changes to the clients in a session. All clients join a room with the same name as the session upon loading. User join/leave, file upload/download and message send/recive have websocket events