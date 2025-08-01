import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, emit, join_room
import datetime
import eventlet
eventlet.monkey_patch()

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sarthi.db'
app.config['JWT_SECRET_KEY'] = 'super-secret-key'
db = SQLAlchemy(app)
jwt = JWTManager(app)
socketio = SocketIO(app, cors_allowed_origins="*")


# --------------------- MODELS ---------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    city = db.Column(db.String(100))

    # Survey traits
    diet = db.Column(db.String(20))
    personality = db.Column(db.String(20))
    sleep_habit = db.Column(db.String(20))
    noise_tolerance = db.Column(db.String(20))
    smoke_alcohol = db.Column(db.String(20))


class Preference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    preferred_gender = db.Column(db.String(10))
    max_rent = db.Column(db.Integer)
    location = db.Column(db.String(100))


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    message = db.Column(db.String(300))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.String(1000))
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)


# --------------------- ROUTES ---------------------
@app.route("/")
def home():
    return "Sarthi Backend with Chat is Running!"


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"message": "User already exists"}), 400

    hashed_pw = generate_password_hash(data['password'])
    user = User(name=data['name'], email=data['email'], password_hash=hashed_pw)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User registered successfully!"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({"message": "Invalid credentials"}), 401
    token = create_access_token(identity=user.id, expires_delta=datetime.timedelta(days=1))
    return jsonify(token=token, user={"id": user.id, "email": user.email, "name": user.name})


@app.route("/profile", methods=["GET", "PUT"])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if request.method == "GET":
        return jsonify({
            "name": user.name, "email": user.email,
            "age": user.age, "gender": user.gender, "city": user.city,
            "diet": user.diet, "personality": user.personality,
            "sleep_habit": user.sleep_habit, "noise_tolerance": user.noise_tolerance,
            "smoke_alcohol": user.smoke_alcohol
        })
    else:
        data = request.get_json()
        user.name = data.get('name', user.name)
        user.age = data.get('age', user.age)
        user.gender = data.get('gender', user.gender)
        user.city = data.get('city', user.city)
        db.session.commit()
        return jsonify({"message": "Profile updated successfully"})


@app.route("/preferences", methods=["POST"])
@jwt_required()
def set_preferences():
    user_id = get_jwt_identity()
    data = request.get_json()
    pref = Preference.query.filter_by(user_id=user_id).first()
    if not pref:
        pref = Preference(user_id=user_id)
    pref.preferred_gender = data['preferred_gender']
    pref.max_rent = data['max_rent']
    pref.location = data['location']
    db.session.add(pref)
    db.session.commit()
    return jsonify({"message": "Preferences saved!"})


@app.route("/traits", methods=["GET", "POST"])
@jwt_required()
def traits():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if request.method == "GET":
        return jsonify({
            "diet": user.diet,
            "personality": user.personality,
            "sleep_habit": user.sleep_habit,
            "noise_tolerance": user.noise_tolerance,
            "smoke_alcohol": user.smoke_alcohol
        })

    data = request.get_json()
    user.diet = data.get("diet", user.diet)
    user.personality = data.get("personality", user.personality)
    user.sleep_habit = data.get("sleep_habit", user.sleep_habit)
    user.noise_tolerance = data.get("noise_tolerance", user.noise_tolerance)
    user.smoke_alcohol = data.get("smoke_alcohol", user.smoke_alcohol)
    db.session.commit()
    return jsonify({"message": "Traits updated successfully"})


@app.route("/match", methods=["GET"])
@jwt_required()
def match():
    user_id = get_jwt_identity()
    me = User.query.get(user_id)
    my_pref = Preference.query.filter_by(user_id=user_id).first()

    if not me or not my_pref:
        return jsonify({"message": "Set your profile/preferences first!"}), 400

    all_users = User.query.filter(User.id != user_id).all()
    matches = []

    for other in all_users:
        score = 0

        if me.diet == other.diet:
            score += 20
        if me.personality == other.personality:
            score += 20
        if me.sleep_habit == other.sleep_habit:
            score += 15
        if me.noise_tolerance == other.noise_tolerance:
            score += 15
        if me.smoke_alcohol == other.smoke_alcohol:
            score += 30

        matches.append({
            "id": other.id,
            "name": other.name,
            "city": other.city,
            "compatibility_score": score
        })

    matches.sort(key=lambda x: x["compatibility_score"], reverse=True)
    return jsonify(matches)


@app.route("/feedback", methods=["POST"])
@jwt_required()
def feedback():
    user_id = get_jwt_identity()
    data = request.get_json()
    fb = Feedback(user_id=user_id, message=data['message'])
    db.session.add(fb)
    db.session.commit()
    return jsonify({"message": "Feedback submitted!"})


@app.route("/messages/<int:receiver_id>", methods=["GET"])
@jwt_required()
def get_messages(receiver_id):
    sender_id = get_jwt_identity()
    msgs = Message.query.filter(
        ((Message.sender_id == sender_id) & (Message.receiver_id == receiver_id)) |
        ((Message.sender_id == receiver_id) & (Message.receiver_id == sender_id))
    ).order_by(Message.timestamp).all()

    return jsonify([
        {
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "content": m.content,
            "timestamp": m.timestamp.isoformat()
        } for m in msgs
    ])


# --------------------- SOCKET EVENTS ---------------------
@socketio.on('send_message')
def handle_send_message(data):
    sender_id = data['sender_id']
    receiver_id = data['receiver_id']
    content = data['content']

    msg = Message(sender_id=sender_id, receiver_id=receiver_id, content=content)
    db.session.add(msg)
    db.session.commit()

    room = f"chat_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    emit('receive_message', {
        'sender_id': sender_id,
        'receiver_id': receiver_id,
        'content': content,
        'timestamp': str(msg.timestamp)
    }, room=room)


@socketio.on('join_room')
def handle_join(data):
    sender_id = data['sender_id']
    receiver_id = data['receiver_id']
    room = f"chat_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    join_room(room)


# --------------------- MAIN ---------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)

