import io
import os
import random
import secrets
import shutil
import string
import uuid
from mimetypes import guess_type

import filetype
from flask import (Blueprint, Flask, after_this_request, redirect,
                   render_template, request, send_file, session, url_for)
from flask_socketio import SocketIO, emit, join_room

# App init
app = Flask(__name__)
app.secret_key = b'\xa6\xa2GX\x19x/\xb5HI\xe3\x9b\xa3[\xd6\xda'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 1024**3

socketio = SocketIO(app)

STORE = '.\\store'

# These could be replaced by a database or something
# Also merge rooms and files?
rooms = {} # {<s_name>: [<list of sids>]}
users = {} # {<sid>: {'uname', 'room', 'colour', 'sid'}}
files = {} # {<s_name>: {<f_name> : {'sender', 'dir', 'tokens'}}}

# Page Routes

@app.route('/', methods=['GET', 'POST'])
def index():
    '''
    Currently quite basic homepage
    '''
    if request.method == 'POST':
        f = request.form
        session['uname'] = f.get('user-name')

        return redirect(url_for('in_session', s_name=f['session']))

    return render_template("index.html")

@app.route('/s/<s_name>')
def in_session(s_name):
    '''
    the actual session
    '''
    ensure_uname(session)

    # Set up session, etc.
    if s_name in files:
        f_names = list(files[s_name].keys())
    else:
        files[s_name] = {}
        f_names = []
        store = os.path.join(STORE, s_name)

        try:
            shutil.rmtree(store)
        except FileNotFoundError:
            pass

        os.makedirs(store)

    if s_name not in rooms: rooms[s_name] = []

    ulist = [
        {
            'uname' : users[user]['uname'],
            'colour' : users[user]['colour']
        } for user in rooms[s_name]
    ]

    return render_template("session.html", s_name=s_name, ulist=ulist, uname=session['uname'])

# Back Routes

# TODO: Automatically determine room from session
@app.route('/upload/<s_name>', methods=['GET', 'POST'])
def upload(s_name):
    '''
    Backend for uploading a file
    Adds the file to the session ensuring the filename is ok
    Warning: downloads file to disk
    '''

    if request.method == 'POST':
        f = request.files.get('file')

        if f == None:
            return 'Error: No file attached', 400

        f_name = f.filename
        ofn, ext = os.path.splitext(f_name)
        store = os.path.join(STORE, s_name)

        # Avoid Duplicate files
        i = 1
        while os.path.exists(os.path.join(store, f_name)):
            f_name = ofn + '(' + str(i) + ')' + ext
            i += 1

        f_path = os.path.join(store, f_name)
        f.save(f_path)
        if s_name not in files: files[s_name] = {}
        files[s_name][f_name] = {'sender': session['uname'], 'dir': f_path, 'tokens': []}

        print(f'{session["uid"]} : {session["uname"]} uploaded file {f_name} from {s_name}')

        # TODO: this helper is unessacary, could be brought back and streamlined
        issue_room_tokens(s_name, f_name, session['uname'], f_path)

        return 'successful', 200

    return 'Use POST to upload file', 400

# TODO: Automatically determine room from session
@app.route('/download/<s_name>/<f_name>')
def download(s_name, f_name):
    '''
    Backend for downloading a file
    Also handles authentication and removal of stale files
    '''

    if s_name not in files or f_name not in files[s_name]:
        return 'Error: File not found', 404
    
    f_entry = files[s_name][f_name]

    if session['uid'] not in f_entry['tokens']:
        return 'Error: User cannot download file or has already downloaded the file', 403

    file_path = f_entry['dir']

    return_data = io.BytesIO()
    with open(file_path, 'rb') as f:
        return_data.write(f.read())
    return_data.seek(0)

    @after_this_request
    def after(response):
        socketio.emit('remove_file', {'file': f_name}, to=users[session['uid']]['sid'])
        files[s_name][f_name]['tokens'].remove(session['uid'])

        if files[s_name][f_name]['tokens'] == []:
            os.remove(file_path)
            del files[s_name][f_name]

        print(f'{session["uid"]} : {session["uname"]} download file {f_name} from {s_name}')
        return response

    return send_file(return_data, mimetype=guess_type(f_name)[0],
                     attachment_filename=f_name,
                     as_attachment=True)

# SocketIO

@socketio.on('connect')
def on_connect():
    print(f'{session["uid"]} : {session["uname"]} connected')
    session['sid'] = request.sid
    pass

@socketio.on('disconnect')
def on_disconnect():
    user = session['uid']
    if user in users:
        room = users[user]['room']
        print(f'{user} : {users[user]["uname"]} disconnected from {room}')

        # remove files
        if room in files:
            x = list(files[room].items())
            for name, entry in x:
                if entry['sender'] == users[user]["uname"]:
                    os.remove(entry['dir'])
                    del files[room][name]

        rooms[room].remove(user)
        send_user_leave(room, users[session['uid']])
        del users[user]

    else:
        print(f'{user} : disconnected')

@socketio.on('join')
def on_join(room):
    join_room(room)

    ensure_uname(session)

    users[session['uid']] = {'room': room, 'uname': session['uname'], 'sid': request.sid}

    if room in rooms:
        rooms[room].append(session['uid'])
    else:
        rooms[room] = [session['uid']]

    users[session['uid']]['colour'] = get_new_colour(room)

    print(f'{session["uid"]} : {session["uname"]} joined room {room}')
    session['room'] = room
    send_user_join(room, users[session['uid']])

@socketio.on('leave')
def on_leave(room):
    rooms[room].remove(request.sid)
    del session['room']

    send_user_leave(room, users[session['uid']])

    # Clean up old rooms
    if not rooms[room]:
        del rooms[room]

@socketio.on('sendmsg')
def msg_sent(msg):
    if not 'room' in session:
        print(f'{session["uid"]} : WARNING : sent message whilst not in room')
        return
    
    print(f'{session["uid"]} : {session["uname"]} wrote {msg} to {session["room"]}')

    socketio.emit('recivemsg', {
        'sender': session['uname'],
        'content': msg
    }, to=session['room'])

# Helper functions

def issue_room_tokens(s_name, f_name, sender, f_path):
    f_type = filetype.guess(f_path)
    
    for user in rooms[s_name]:
        files[s_name][f_name]['tokens'].append(user)
        socketio.emit('add_file',
            {'file': f_name, 'url': url_for('download', s_name=s_name, f_name=f_name),
            'sender': sender, 'f_type': f_type.mime if f_type else '?', 'f_size': format_bytes(os.path.getsize(f_path))},
            to=users[user]['sid'])

def send_user_join(room, user):
    socketio.emit('ujoin', {
        'uname': user['uname'],
        'colour': user['colour'],
        'count': len(rooms[room])
    }, to=room)

def send_user_leave(room, user):
    socketio.emit('uleave', {
        'uname': user['uname'],
        'count': len(rooms[room])
    }, to=room)

def format_bytes(size):
    power = 2**10
    n = 0
    labels = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + labels[n]

def ensure_uname(session):
    '''
    ensure session has id and uname
    '''

    if not 'uname' in session:
        # TODO: generate proper guest strings
        session['uname'] = 'Guest-' + ''.join((random.choice(string.ascii_letters) for _ in range(5)))

    # ensure username is unique to prevent imitation
    # and also make my life easier by allowing messages to be sent by username

    oun = session['uname']
    i = 1
    while session['uname'] in [user['uname'] for user in users.values()]:
        session['uname'] = oun + str(i)
        i += 1

    # Generate uid
    # Should only run once but better safe than sorry
    if 'uid' not in session:
        uid = None
        while not uid or uid in users:
            uid = uuid.uuid4().hex
        
        session['uid'] = uid

valid_colours = ['red', 'pink', 'blue', 'aqua', 'green', 'yellow']
def get_new_colour(room):
    '''
    Issue a new, unused colour
    If all colours have been issued, start again
    '''
    if room not in rooms: return valid_colours[0]
    used_colours = [users[user]['colour'] for user in rooms[room] if 'colour' in users[user]]

    sentiel = object()
    while (colour := next((x for x in valid_colours if x not in used_colours), sentiel)) == sentiel:
        for x in valid_colours: used_colours.remove(x)

    return colour

if __name__ == '__main__':
    # ensure store is present and empty
    try:
        shutil.rmtree(STORE)
    except FileNotFoundError:
        pass

    os.makedirs(STORE)

    socketio.run(app, host="0.0.0.0")
