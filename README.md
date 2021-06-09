# Seadrop - Simplifying file transfers

This is a prototype application to demonstrate the concept of Seadrop.

Things that need changing between this prototype and release are detailed below.

# Current architecture

## Pages

### Frontend

#### `[GET] /`
Landing page, allows users to join sessions.

#### `[GET] /s/<session>`
Session page, allows users to upload and download files.

Listens on websocket room.

### Backend

#### `[POST] /upload/<session>`
Endpoint for uploading files to a session.
Upload a single file as `file`.

#### `[GET] /download/<session>/<file>`
Endpoint for downloading a file.
Will delete file once downloaded.

## Websocket Details

Websockets are used to communicate changes to the clients in a session.

All clients join a room with the same name as the session upon loading.

### Message `add_file`
Emmitted when a file is uploaded to a session.

### Message `remove_file`
Emmitted when a file is downloaded from a session and thus deleted.

# Future Changes

The current main consideration is what the end product should look like;
+ If it is to remain as a small self-hosted system many of these aren't a priority or even nessacary.
+ If it is to become an actual hosted service everything here needs to be considered and even more past that.

## Random TODOs:
Things that should be done eventually.
```
? Chat system?
    . Kinda opens up a bunch of other considerations
    . Don't really see much value to the user

? Allow users to preview files?
    . Might conflict with the whole single access thing
    . Although don't want users to accidently download something horrific

? Reconsider model to remove server hosting of files
    ! If Alice stores the file then she can disconnect early
        . Meaning Bob can't get it
    ! If Bob stores file Alice could send something bad
        . Large - could use up all of the RAM
        . Just bad - stuff Bob doesn't want
    . i.e. If Alice is sending a message to Bob
    . Alice says she has the file
    . Bob requests it and Alice sends it

~ Make the site look good
    ~ Make the logo look good
    * Create actual branding
~ Do some kind of HCI review
    . Ensure workflow is ok
    . Ensure visuals are ok

* Add TOS
    . Basically what users aren't allowed to do
* Add Privacy statement
    . What information we store
    . What we do with it
! Both of above shouldn't be written in legalese, only in plain english
    . This is due to summaries being held as the actual legal text
    . No need to if not fully hosted

* Add about pages
    . How seadrop works
    . Explain TOS and Privacy in simple terms

* Found a company ig
    ! Would probably come with obligations I don't want to deal with
    * Monatisation should only be through ads/pay for no ads
        . Don't want to make this into a big subscription so frame as a supporter
* Find someone to hit me with a rolled up newspaper every time I consider turning this into a startup

? Alternate platforms?
    ? Desktop App?
    ? Chat integrations?
    ? Virtual Network drives?
        . See the seadrop session as a permanent folder on your PC
    ? Physical Drives?
```
## Password protected Sessions
Basic level of security.
```
~ Sessions move from ad-hoc to creation based
    ~ /s/ route checks for existing session
    * create session route
    ? session auth route?

    + Add create button
~ Sessions can require a password to join
+ Allow sessions to be joined with an invite link
```
## Users in room
Intent is to make the site easier to use.
```
* Create list of users in current room
    + Add nicknames for joining users
    * Create server side store of current sessions
        . Will also store users in session
        . Doesn't need to be persistent
    * Add websocket listeners for people joining and leaving a room
        . Ensure client communicates current room
        . Ensure server communicates nickname

~ Instead of sending a file to the server that one user can download, send each file once to each user
    . Only sends file to users currently in session
    + Add list of uploaded files to session store
    + Add list of valid single use access tokens for a file
    ~ Modify upload endpoint to add file to session store
        + Generates access tokens
        + Distributes access tokens to each user
    ~ Modify download endpoint to require access tokens
        ? Token could also point to file for reduction of ambiguity
        ? Token could be time gated instead of single use
            . I've just made snapchat but worse haven't I?
        + Ensure token is consumed (i.e. removed from list) upon use

~ Allow users to also send files to an individual user
    ? Modify session page to give each user a bigger UI element?
    + Allow user to drag file onto an individual user to send the file directly
        . Ensure the UI clearly indicates what you will do with the file
```
## End-to-End encryption
Allows users to trust Seadrop.
```
~ Each file is encrypted before upload to each user
    ! Server now cannot read files (See logging below)
    ~ Modify /upload to encrypt each file CLIENT SIDE before sending
    ~ Modify /download to decrypt each file CLIENT SIDE before saving
    ! for both above DO NOT WRITE THE ENCRYPTION YOURSELF. IRIS.
        . You will get it wrong and leave things vulnrable
    * Send key to users on upload
        . Decryption key sent end-to-end encrypted
```
## User Account controls
Intent is to allow users to veify who is reciving the files.
```
* Add user accounts
    + Allow existing functionality to continue by using guest logins
        ! Potential for abuse, Hard to ban multiple guest accounts
        ? Reduced permissions for guest accounts
            . Inablility to send files would be an easy prevention
            . Inablility to create sessions might just be inconvinient
    * Allow users to create accounts

+ Add methods to allow users to verify other users itentities
    + Allow users to link to third party accounts
        + Allow users to display usernames of other accounts when joining sessions
        + Allow users to send invites with passwords encoded
        + Allow users to send invites that can only be opened by specific users
```
## Abuse of system/Illegal Content/etc.

Prevent spam, harrassment and crimes.

Logging is in aid of helping the police catch criminals, not creating a surveliance state.

Can probably be left for a while, if this stays small it won't be nessacary.
```
* Integrated virus scanning
	+ Add an extra button that scans the file

* Log uploads by hash
    ~ Modify /upload to attach a hash to the uploaded file
        . Will need to develop some form of content ID akin to YouTube's solution
    * Add logging database that stores the file hash and the senders and recipients
        . Could log if they actually downloaded it or not

? Content ID system ideas
    . Run some kind of image recognition algorithm on the image client side
        . Or at least on an anonymous server
    . On the server side we can compare this to a database
        . Rely on a third party to provide the comparison sets for illegal content
    . Could also use this to flag potentially NSFW uploads to prevent people from seeing bad things

* Log user activity
    . Allows us to tie multiple different uploads together
    . Same kind of tracking not possible on guests

! IP address logging
    . Could be deemed too risky, don't want leaks of confidential info
```