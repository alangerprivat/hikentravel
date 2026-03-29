import os
import json
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
database_url = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/hikentravel')
# Handle postgres:// vs postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAPY_API_KEY'] = os.getenv('MAPY_API_KEY', '')

# Admin credentials from environment
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def set_password(self, password):
        self.password = generate_password_hash(password)


class Category(db.Model):
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    icon = db.Column(db.String(50), default='🏔️')
    color = db.Column(db.String(7), default='#3DB88C')
    hikes = db.relationship('Hike', backref='category', lazy=True, cascade='all, delete-orphan')


class Hike(db.Model):
    __tablename__ = 'hike'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    region = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    elevation_gain = db.Column(db.Float, nullable=True)
    elevation_loss = db.Column(db.Float, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False)
    difficulty = db.Column(db.Integer, default=3)  # 1-5
    trail_type = db.Column(db.String(50), default='loop')  # loop, out-and-back, point-to-point
    start_lat = db.Column(db.Float, nullable=False)
    start_lng = db.Column(db.Float, nullable=False)
    end_lat = db.Column(db.Float, nullable=True)
    end_lng = db.Column(db.Float, nullable=True)
    gpx_data = db.Column(db.Text, nullable=True)
    tags = db.Column(db.String(500), nullable=True)
    rating = db.Column(db.Integer, nullable=True)  # 1-5
    notes = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_tags_list(self):
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',')]
        return []

    def get_difficulty_stars(self):
        return '🏔️' * self.difficulty

    def get_duration_display(self):
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if hours > 0 and mins > 0:
            return f"{hours}h {mins}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{mins}m"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def init_admin_user():
    """Initialize admin user if it doesn't exist"""
    if User.query.filter_by(username=ADMIN_USER).first() is None:
        admin = User(username=ADMIN_USER)
        admin.set_password(ADMIN_PASS)
        db.session.add(admin)
        db.session.commit()


def init_sample_categories():
    """Initialize sample categories"""
    if Category.query.count() == 0:
        categories = [
            Category(name='Berg', icon='⛰️', color='#3DB88C'),
            Category(name='Wald', icon='🌲', color='#2D5A40'),
            Category(name='See', icon='💧', color='#1A8FA3'),
            Category(name='Gebirge', icon='🏔️', color='#8B4513'),
        ]
        for cat in categories:
            db.session.add(cat)
        db.session.commit()


# Routes
@app.before_request
def before_request():
    db.create_all()
    init_admin_user()
    init_sample_categories()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category', type=int)
    difficulty = request.args.get('difficulty', type=int)
    sort_by = request.args.get('sort', 'created_at')

    query = Hike.query

    if search:
        query = query.filter(Hike.name.ilike(f'%{search}%'))

    if category_id:
        query = query.filter_by(category_id=category_id)

    if difficulty:
        query = query.filter_by(difficulty=difficulty)

    if sort_by == 'name':
        query = query.order_by(Hike.name)
    elif sort_by == 'distance':
        query = query.order_by(Hike.distance_km.desc())
    elif sort_by == 'rating':
        query = query.order_by(Hike.rating.desc())
    else:  # created_at
        query = query.order_by(Hike.created_at.desc())

    hikes = query.all()
    categories = Category.query.all()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'hikes': [{
                'id': h.id,
                'name': h.name,
                'region': h.region,
                'distance_km': h.distance_km,
                'elevation_gain': h.elevation_gain,
                'difficulty': h.difficulty,
                'duration_minutes': h.duration_minutes,
                'category': h.category.name if h.category else None,
                'start_lat': h.start_lat,
                'start_lng': h.start_lng,
            } for h in hikes]
        })

    return render_template('index.html', hikes=hikes, categories=categories, 
                         search=search, category_id=category_id, difficulty=difficulty, sort_by=sort_by)


@app.route('/hike/<int:hike_id>')
def hike_detail(hike_id):
    hike = Hike.query.get_or_404(hike_id)
    map_coords = {
        'start': {'lat': hike.start_lat, 'lng': hike.start_lng},
        'end': {'lat': hike.end_lat, 'lng': hike.end_lng} if hike.end_lat and hike.end_lng else None,
        'gpx': hike.gpx_data
    }
    return render_template('hike_detail.html', hike=hike, map_coords=json.dumps(map_coords))


@app.route('/hike/new', methods=['GET', 'POST'])
@login_required
def create_hike():
    if request.method == 'POST':
        try:
            hike = Hike(
                name=request.form.get('name'),
                description=request.form.get('description'),
                region=request.form.get('region'),
                country=request.form.get('country'),
                distance_km=float(request.form.get('distance_km', 0)),
                elevation_gain=float(request.form.get('elevation_gain') or 0),
                elevation_loss=float(request.form.get('elevation_loss') or 0),
                duration_minutes=int(request.form.get('duration_minutes', 60)),
                difficulty=int(request.form.get('difficulty', 3)),
                trail_type=request.form.get('trail_type', 'loop'),
                start_lat=float(request.form.get('start_lat')),
                start_lng=float(request.form.get('start_lng')),
                end_lat=float(request.form.get('end_lat') or 0) or None,
                end_lng=float(request.form.get('end_lng') or 0) or None,
                tags=request.form.get('tags'),
                notes=request.form.get('notes'),
                category_id=request.form.get('category_id', type=int),
            )

            if 'gpx_file' in request.files:
                gpx_file = request.files['gpx_file']
                if gpx_file and gpx_file.filename.endswith('.gpx'):
                    hike.gpx_data = gpx_file.read().decode('utf-8')

            db.session.add(hike)
            db.session.commit()
            return redirect(url_for('hike_detail', hike_id=hike.id))
        except Exception as e:
            db.session.rollback()
            return render_template('hike_form.html', categories=Category.query.all(), error=str(e))

    return render_template('hike_form.html', categories=Category.query.all())


@app.route('/hike/<int:hike_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_hike(hike_id):
    hike = Hike.query.get_or_404(hike_id)

    if request.method == 'POST':
        try:
            hike.name = request.form.get('name')
            hike.description = request.form.get('description')
            hike.region = request.form.get('region')
            hike.country = request.form.get('country')
            hike.distance_km = float(request.form.get('distance_km', 0))
            hike.elevation_gain = float(request.form.get('elevation_gain') or 0)
            hike.elevation_loss = float(request.form.get('elevation_loss') or 0)
            hike.duration_minutes = int(request.form.get('duration_minutes', 60))
            hike.difficulty = int(request.form.get('difficulty', 3))
            hike.trail_type = request.form.get('trail_type', 'loop')
            hike.start_lat = float(request.form.get('start_lat'))
            hike.start_lng = float(request.form.get('start_lng'))
            hike.end_lat = float(request.form.get('end_lat') or 0) or None
            hike.end_lng = float(request.form.get('end_lng') or 0) or None
            hike.tags = request.form.get('tags')
            hike.notes = request.form.get('notes')
            hike.category_id = request.form.get('category_id', type=int)
            hike.rating = request.form.get('rating', type=int)

            if 'gpx_file' in request.files:
                gpx_file = request.files['gpx_file']
                if gpx_file and gpx_file.filename.endswith('.gpx'):
                    hike.gpx_data = gpx_file.read().decode('utf-8')

            db.session.commit()
            return redirect(url_for('hike_detail', hike_id=hike.id))
        except Exception as e:
            db.session.rollback()
            return render_template('hike_form.html', hike=hike, categories=Category.query.all(), error=str(e))

    return render_template('hike_form.html', hike=hike, categories=Category.query.all())


@app.route('/hike/<int:hike_id>/delete', methods=['POST'])
@login_required
def delete_hike(hike_id):
    hike = Hike.query.get_or_404(hike_id)
    db.session.delete(hike)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/hike/<int:hike_id>/gpx')
def download_gpx(hike_id):
    hike = Hike.query.get_or_404(hike_id)

    if hike.gpx_data:
        gpx_content = hike.gpx_data
    else:
        gpx_content = generate_gpx(hike)

    filename = secure_filename(hike.name) + '.gpx'
    return send_file(
        __import__('io').BytesIO(gpx_content.encode('utf-8')),
        mimetype='application/gpx+xml',
        as_attachment=True,
        download_name=filename
    )


def generate_gpx(hike):
    """Generate GPX XML from hike data"""
    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="HikeNTravel"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns="http://www.topografix.com/GPX/1/1"
  xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>{hike.name}</name>
    <desc>{hike.description or ''}</desc>
    <time>{hike.created_at.isoformat()}Z</time>
  </metadata>
  <wpt lat="{hike.start_lat}" lon="{hike.start_lng}">
    <name>{hike.name} - Start</name>
  </wpt>"""

    if hike.end_lat and hike.end_lng:
        gpx += f"""
  <wpt lat="{hike.end_lat}" lon="{hike.end_lng}">
    <name>{hike.name} - End</name>
  </wpt>"""

    gpx += """
  <trk>
    <name>{}</name>
    <trkseg>
      <trkpt lat="{}" lon="{}">
        <name>Start</name>
      </trkpt>
    </trkseg>
  </trk>
</gpx>""".format(hike.name, hike.start_lat, hike.start_lng)

    return gpx


@app.route('/api/hike/map-data')
def get_map_data():
    """Get all hikes for map display"""
    hikes = Hike.query.all()
    return jsonify({
        'hikes': [{
            'id': h.id,
            'name': h.name,
            'lat': h.start_lat,
            'lng': h.start_lng,
            'difficulty': h.difficulty,
            'category': h.category.name if h.category else None,
        } for h in hikes]
    })


if __name__ == '__main__':
    app.run(debug=True)