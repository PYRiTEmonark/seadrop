import os
import random
import secrets
import shutil
import string
import io
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
users = {} # {<sid>: {'uname', 'room', 'colour'}}
files = {} # {<s_name>: {<f_name> : {'sender', 'dir', 'tokens'}}}

# Page Routes

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        f = request.form
        session['uname'] = f.get('user-name')

        return redirect(url_for('in_session', s_name=f['session']))

    return render_template("index.html")

@app.route('/s/<s_name>')
def in_session(s_name):
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

@app.route('/upload/<s_name>', methods=['GET', 'POST'])
def upload(s_name):

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
        files[s_name][f_name] = {'sender': session['uname'], 'dir': f_path, 'tokens': {}}

        print(f'upload : file {f_name} from {s_name}')
        
        # TODO: this helper is unessacary, could be brought back and streamlined
        issue_room_tokens(s_name, f_name, session['uname'], f_path)

        return 'successful', 200
    
    return 'Use POST to upload file', 400

@app.route('/download/<s_name>/<f_name>')
def download(s_name, f_name):
    token = request.args.get('token')

    if s_name not in files:
        return 'Error: File not found', 404

    if f_name not in files[s_name]:
        return 'Error: File not found', 404
    
    f_entry = files[s_name][f_name]

    if token not in f_entry['tokens']:
        return 'Error: Token not in file', 403

    file_path = f_entry['dir']

    return_data = io.BytesIO()
    with open(file_path, 'rb') as f:
        return_data.write(f.read())
    return_data.seek(0)

    @after_this_request
    def after(response):
        socketio.emit('remove_file', {'file': f_name}, to=f_entry['tokens'][token])
        files[s_name][f_name]['tokens'].pop(token)

        if files[s_name][f_name]['tokens'] == []:
            os.remove(file_path)
            del files[s_name][f_name]

        print(f'download : file {f_name} from {s_name}')
        return response

    return send_file(return_data, mimetype=guess_type(f_name)[0],
                     attachment_filename=f_name,
                     as_attachment=True)

# SocketIO

@socketio.on('connect')
def on_connect():
    print(f'{request.sid} : connected')
    session['sid'] = request.sid
    pass

@socketio.on('disconnect')
def on_disconnect():
    user = request.sid
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
        send_user_leave(room, users[request.sid])
        del users[user]

    else:
        print(f'{user} : disconnected')

@socketio.on('join')
def on_join(room):
    join_room(room)

    ensure_uname(session)

    users[request.sid] = {'room': room, 'uname': session['uname']}

    if room in rooms:
        rooms[room].append(request.sid)
    else:
        rooms[room] = [request.sid]

    users[request.sid]['colour'] = get_new_colour(room)

    print(f'{request.sid} : {session["uname"]} joined room {room}')
    session['room'] = room
    send_user_join(room, users[request.sid])

@socketio.on('leave')
def on_leave(room):
    rooms[room].remove(request.sid)
    del session['room']

    send_user_leave(room, users[request.sid])

    # Clean up old rooms
    if not rooms[room]:
        del rooms[room]

@socketio.on('sendmsg')
def msg_sent(msg):
    if not 'room' in session:
        print(f'{request.sid} : WARNING : sent message whilst not in room')
        return
    
    print(f'{request.sid} : relaying message {msg}')

    socketio.emit('recivemsg', {
        'sender': session['uname'],
        'content': msg
    }, to=session['room'])

# Helper functions

def issue_room_tokens(s_name, f_name, sender, f_path):
    for user in rooms[s_name]:
        token = secrets.token_urlsafe()
        files[s_name][f_name]['tokens'][token] = user
        f_type = filetype.guess(f_path)
        socketio.emit('add_file',
            {'file': f_name, 'url': url_for('download', s_name=s_name, f_name=f_name, token=token),
            'sender': sender, 'f_type': f_type.mime if f_type else '?', 'f_size': format_bytes(os.path.getsize(f_path))},
            to=user)

# def send_room_update(room):
    # ulist = {users[user]['uname'] : users[user]['colour'] for user in rooms[room]}
    # socketio.emit('update', {'ulist': ulist, 'count': len(ulist)}, to=room)

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
    if not 'uname' in session:
        # TODO: generate proper guest strings
        session['uname'] = 'Guest-' + ''.join((random.choice(string.ascii_letters) for _ in range(5)))

    # ensure username is unique to prevent imitation
    # and also make my life easier by allowing messages to be sent by username
    # this removes the need for some convoluted id
    # note that there is a small chance that two people will get the same guest string

    oun = session['uname']
    i = 1
    while session['uname'] in [user['uname'] for user in users.values()]:
        session['uname'] = oun + str(i)
        i += 1

# Issue a new, unused colour
# If all colours have been issued, start again
# TODO: Reconsider this?
valid_colours = ['red', 'pink', 'blue', 'aqua', 'green', 'yellow']
def get_new_colour(room):
    if room not in rooms: return valid_colours[0]
    used_colours = [users[user]['colour'] for user in rooms[room] if 'colour' in users[user]]

    while (colour := next((x for x in valid_colours if x not in used_colours), None)) == None:
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