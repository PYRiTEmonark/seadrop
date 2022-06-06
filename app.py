import io
import json
import os
import random
import shutil
import string
import uuid
from mimetypes import guess_type

import filetype
from flask import (Flask, after_this_request, escape, flash, redirect,
                   render_template, request, send_file, session, url_for)
from flask_socketio import SocketIO, emit, join_room

from utils import format_bytes, sanitize

# App init
app = Flask(__name__)
with open('config.json') as config_file:
    config_data = json.load(config_file)

# Secret key is randomized to prevent sessions being carried over
# Does cause join listener to crap itself all over log
app.secret_key = os.urandom(30).hex()

app.config.update(config_data['app'])

socketio = SocketIO(app)

# These could be replaced by a database or something
# Also merge rooms and files?
rooms = {} # {<room_name>: [<list of sids>]}
files = {} # {<room_name>: {<f_name> : {'sender', 'dir', 'tokens'}}}
users = {} # {<uid>: {'uname', 'rooms', 'colour', 'sid'}}

# Page Routes

@app.route('/', methods=['GET', 'POST'])
def index():
    '''
    Currently quite basic homepage
    '''

    session['room'] = ''

    # if session.get('room'):
    #     return redirect(url_for('in_session', room_name=session['room']))

    if request.method == 'POST':
        f = request.form
        # if not ('uname' in session and session['uname']):
        session['uname'] = sanitize(f.get('user-name'))

        return redirect(url_for('in_session', room_name=f['session']))

    return render_template("index.html")

@app.route('/s/<room_name>')
def in_session(room_name):
    '''
    the actual session
    '''
    ensure_uname(session)

    print(session['uname'], 'joining', room_name)

    # Set up room filestore
    if room_name not in files:
        files[room_name] = {}
        store = os.path.join(app.config['FILE_STORE'], room_name)

        try:
            shutil.rmtree(store)
        except FileNotFoundError:
            pass

        os.makedirs(store)

    if room_name not in rooms:
        rooms[room_name] = []


    # User does not join session until the join message
    # session['room'] = room_name

    ulist = [
        {
            'uname' : users[user]['uname'],
            'colour' : users[user]['colour']
        } for user in rooms[room_name] if user in users
    ]
    print('users already in room:', ulist)

    return render_template("room.html", room_name=room_name, ulist=ulist, uname=session['uname'])

# Back Routes

@app.route('/upload/<room_name>', methods=['GET', 'POST'])
def upload(room_name):
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
        store = os.path.join(app.config['FILE_STORE'], room_name)

        # Avoid Duplicate files
        i = 1
        while os.path.exists(os.path.join(store, f_name)):
            f_name = ofn + '(' + str(i) + ')' + ext
            i += 1

        f_path = os.path.join(store, f_name)
        f.save(f_path)
        if room_name not in files: files[room_name] = {}
        files[room_name][f_name] = {'sender': session['uname'], 'dir': f_path, 'tokens': []}

        print(f'{session["uid"]} : {session["uname"]} uploaded file {f_name} from {room_name}')

        # TODO: this helper is unessacary, could be brought back and streamlined
        issue_room_tokens(room_name, f_name, session['uname'], f_path)

        return 'successful', 200

    return 'Use POST to upload file', 400

@app.route('/download/<room_name>/<f_name>')
def download(room_name, f_name):
    '''
    Backend for downloading a file
    Also handles authentication and removal of stale files
    '''

    if room_name not in files or f_name not in files[room_name]:
        return 'Error: File not found', 404
    
    f_entry = files[room_name][f_name]

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
        files[room_name][f_name]['tokens'].remove(session['uid'])

        if files[room_name][f_name]['tokens'] == []:
            os.remove(file_path)
            del files[room_name][f_name]

        print(f'{session["uid"]} : {session["uname"]} download file {f_name} from {room_name}')
        return response

    return send_file(return_data, mimetype=guess_type(f_name)[0],
                     attachment_filename=f_name,
                     as_attachment=True)

# SocketIO

@socketio.on('connect')
def on_connect():
    print(f'{session["uid"]} : {session["uname"]} connected')
    session['sid'] = request.sid

    if session['uid'] in users:
        users[session['uid']]['sid'] = request.sid

@socketio.on('disconnect')
def on_disconnect():
    user = [k for k,v in users.items() if v['sid'] == request.sid][0]
    if user in users:
        room = users[user]['room']
        print(f'{user} : {users[user]["uname"]} disconnected')

        # remove files
        if room in files:
            x = list(files[room].items())
            for name, entry in x:
                if entry['sender'] == users[user]["uname"]:
                    os.remove(entry['dir'])
                    del files[room][name]

        if user in rooms[room]:
            rooms[room].remove(user)
            send_user_leave(room, users[session['uid']])

        if user in users:
            del users[user]

    else:
        print(f'{user} : {session.get("uname")} disconnected')

@socketio.on('join')
def on_join(room):
    join_room(room)

    # ensure_uname(session)
    # if session['room'] == room: return

    # Rejoin on reload
    if session['uid'] in rooms[room]:
        on_leave(room)

    session['room'] = room
    users[session['uid']] = {'room': room, 'uname': session['uname'], 'sid': request.sid}

    if room in rooms:
        rooms[room].append(session['uid'])
    else:
        rooms[room] = [session['uid']]

    users[session['uid']]['colour'] = get_new_colour(room)

    print(f'{session["uid"]} : {session["uname"]} joined room {room}')
    # session['room']
    send_user_join(room, users[session['uid']])

@socketio.on('leave')
def on_leave(room):

    print(f'{session["uid"]} : {session["uname"]} left room {room}')

    rooms[room].remove(session['uid'])
    session['room'] = ''

    send_user_leave(room, users[session['uid']])

    # Clean up old rooms
    if not rooms[room]:
        del rooms[room]

@socketio.on('sendmsg')
def msg_sent(msg):
    msg = sanitize(msg)

    # if not 'room' in session:
    #     print(f'{session["uid"]} : WARNING : sent message whilst not in room')
    #     return

    print(f'{session["uid"]} : {session["uname"]} wrote {msg} to {session["room"]}')

    socketio.emit('recivemsg', {
        'sender': session["uname"],
        'content': msg
    }, to=session['room'])

# Helper functions

def issue_room_tokens(room_name, f_name, sender, f_path):
    f_type = filetype.guess(f_path)
    
    for user in rooms[room_name]:
        files[room_name][f_name]['tokens'].append(user)
        socketio.emit('add_file',
            {'file': f_name, 'url': url_for('download', room_name=room_name, f_name=f_name),
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

def ensure_uname(session):
    '''
    ensure session has id and uname
    '''

    if not 'uname' in session:
        # TODO: generate proper guest strings
        session['uname'] = 'Guest-' + ''.join((random.choice(string.ascii_letters) for _ in range(5)))

    # ensure username is unique to prevent imitation
    # and also make my life easier by allowing messages to be sent by username

    # oun = session['uname']
    # i = 1
    # while session['uname'] in [user['uname'] for user in users.values()]:
    #     session['uname'] = oun + str(i)
    #     i += 1

    session['uname'] = sanitize(session['uname'])

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

    s = object()
    while (colour := next((x for x in valid_colours if x not in used_colours), s)) == s:
        for x in valid_colours: used_colours.remove(x)

    return colour

if __name__ == '__main__':
    # ensure store is present and empty
    try:
        shutil.rmtree(app.config['FILE_STORE'])
    except FileNotFoundError:
        pass

    os.makedirs(app.config['FILE_STORE'])

    app.logger.disabled = True

    socketio.run(app, host="0.0.0.0")
