import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import urllib.request
import urllib.parse

app = Flask(__name__)

# Configuration
database_url = os.getenv('DATABASE_URL', 'postgresql://user:password@localhost/hikentravel')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+pg8000://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+pg8000://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAPY_API_KEY'] = os.getenv('MAPY_API_KEY', '')

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
    icon = db.Column(db.String(50), default='\u26f0\ufe0f')
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
    difficulty = db.Column(db.Integer, default=3)
    trail_type = db.Column(db.String(50), default='loop')
    start_lat = db.Column(db.Float, nullable=False)
    start_lng = db.Column(db.Float, nullable=False)
    end_lat = db.Column(db.Float, nullable=True)
    end_lng = db.Column(db.Float, nullable=True)
    gpx_data = db.Column(db.Text, nullable=True)
    route_geometry = db.Column(db.Text, nullable=True)
    mapy_url = db.Column(db.String(500), nullable=True)
    tags = db.Column(db.String(500), nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_tags_list(self):
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',')]
        return []

    def get_difficulty_stars(self):
        return '\u26f0\ufe0f' * self.difficulty

    def get_duration_display(self):
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if hours > 0 and mins > 0:
            return f"{hours}h {mins}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{mins}m"

class Trip(db.Model):
    __tablename__ = 'trip'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.String(20), nullable=True)
    end_date = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    stops = db.relationship('TripStop', backref='trip', lazy=True, cascade='all, delete-orphan', order_by='TripStop.position')

    def get_total_distance(self):
        total = 0
        for stop in self.stops:
            if stop.distance_to_next_km:
                total += stop.distance_to_next_km
        return round(total, 1)

    def get_total_duration_display(self):
        total_min = 0
        for stop in self.stops:
            if stop.duration_minutes:
                total_min += stop.duration_minutes
            if stop.duration_to_next_min:
                total_min += stop.duration_to_next_min
        hours = total_min // 60
        mins = total_min % 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def get_stop_count(self):
        return len(self.stops)

class TripStop(db.Model):
    __tablename__ = 'trip_stop'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    stop_category = db.Column(db.String(50), default='sehenswuerdigkeit')
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    duration_minutes = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    hike_id = db.Column(db.Integer, db.ForeignKey('hike.id'), nullable=True)
    route_to_next = db.Column(db.Text, nullable=True)
    route_type = db.Column(db.String(20), default='car')
    distance_to_next_km = db.Column(db.Float, nullable=True)
    duration_to_next_min = db.Column(db.Integer, nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)
    hike = db.relationship('Hike', lazy=True)

    def get_category_icon(self):
        icons = {
            'wanderung': '\U0001f6b6',
            'stadt': '\U0001f3d9\ufe0f',
            'sehenswuerdigkeit': '\U0001f4cd',
            'unterkunft': '\U0001f3e8',
            'restaurant': '\U0001f37d\ufe0f',
            'transport': '\U0001f68c',
        }
        return icons.get(self.stop_category, '\U0001f4cd')

    def get_category_label(self):
        labels = {
            'wanderung': 'Wanderung',
            'stadt': 'Stadt',
            'sehenswuerdigkeit': 'Sehenswuerdigkeit',
            'unterkunft': 'Unterkunft',
            'restaurant': 'Restaurant',
            'transport': 'Transport',
        }
        return labels.get(self.stop_category, 'Sonstiges')

    def get_route_type_icon(self):
        icons = {
            'car': '\U0001f697',
            'foot_hiking': '\U0001f6b6',
            'public_transport': '\U0001f68c',
            'bike': '\U0001f6b2',
        }
        return icons.get(self.route_type, '\U0001f697')

class PackingItem(db.Model):
    __tablename__ = 'packing_item'
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trip.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_packed = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='Sonstiges')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_admin_user():
    if User.query.filter_by(username=ADMIN_USER).first() is None:
        admin = User(username=ADMIN_USER)
        admin.set_password(ADMIN_PASS)
        db.session.add(admin)
        db.session.commit()

def migrate_db():
    with db.engine.connect() as conn:
        hike_cols = [
            ('route_geometry', 'TEXT'),
            ('mapy_url', 'VARCHAR(500)'),
        ]
        for col_name, col_type in hike_cols:
            try:
                conn.execute(db.text(f"SELECT {col_name} FROM hike LIMIT 1"))
            except Exception:
                conn.rollback()
                try:
                    conn.execute(db.text(f"ALTER TABLE hike ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    conn.rollback()
        stop_cols = [
            ('photo_url', 'VARCHAR(500)'),
        ]
        for col_name, col_type in stop_cols:
            try:
                conn.execute(db.text(f"SELECT {col_name} FROM trip_stop LIMIT 1"))
            except Exception:
                conn.rollback()
                try:
                    conn.execute(db.text(f"ALTER TABLE trip_stop ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                except Exception:
                    conn.rollback()

def init_sample_categories():
    if Category.query.count() == 0:
        categories = [
            Category(name='Berg', icon='\u26f0\ufe0f', color='#3DB88C'),
            Category(name='Wald', icon='\U0001f332', color='#2D5A40'),
            Category(name='See', icon='\U0001f9ca', color='#1A8FA3'),
            Category(name='Gebirge', icon='\U0001f3d4\ufe0f', color='#8B4513'),
        ]
        for cat in categories:
            db.session.add(cat)
        db.session.commit()

# Routes
@app.before_request
def before_request():
    db.create_all()
    migrate_db()
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
    else:
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
                           search=search, category_id=category_id,
                           difficulty=difficulty, sort_by=sort_by)

@app.route('/hike/<int:hike_id>')
def hike_detail(hike_id):
    hike = Hike.query.get_or_404(hike_id)
    map_coords = {
        'start': {'lat': hike.start_lat, 'lng': hike.start_lng},
        'end': {'lat': hike.end_lat, 'lng': hike.end_lng} if hike.end_lat and hike.end_lng else None,
        'gpx': hike.gpx_data,
        'route_geometry': json.loads(hike.route_geometry) if hike.route_geometry else None
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
                route_geometry=request.form.get('route_geometry'),
                mapy_url=request.form.get('mapy_url'),
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
            hike.route_geometry = request.form.get('route_geometry') or hike.route_geometry
            hike.mapy_url = request.form.get('mapy_url') or hike.mapy_url
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
    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="HikeNTravel" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.topografix.com/GPX/1/1" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
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
      <trkpt lat="{}" lon="{}"><name>Start</name></trkpt>
    </trkseg>
  </trk>
</gpx>""".format(hike.name, hike.start_lat, hike.start_lng)
    return gpx

@app.route('/api/hike/map-data')
def get_map_data():
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

# ==================== TRIP ROUTES ====================

@app.route('/trips')
def trip_list():
    trips = Trip.query.order_by(Trip.created_at.desc()).all()
    return render_template('trip_list.html', trips=trips)

@app.route('/trip/new', methods=['GET', 'POST'])
@login_required
def create_trip():
    if request.method == 'POST':
        try:
            trip = Trip(
                name=request.form.get('name'),
                description=request.form.get('description'),
                start_date=request.form.get('start_date') or None,
                end_date=request.form.get('end_date') or None,
                notes=request.form.get('notes'),
            )
            db.session.add(trip)
            db.session.commit()
            return redirect(url_for('trip_detail', trip_id=trip.id))
        except Exception as e:
            db.session.rollback()
            return render_template('trip_form.html', error=str(e))
    return render_template('trip_form.html')

@app.route('/trip/<int:trip_id>')
def trip_detail(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    stops = TripStop.query.filter_by(trip_id=trip.id).order_by(TripStop.position).all()
    hikes = Hike.query.order_by(Hike.name).all()
    packing_items = PackingItem.query.filter_by(trip_id=trip.id).order_by(PackingItem.category, PackingItem.id).all()
    stop_data = []
    for stop in stops:
        sd = {
            'id': stop.id,
            'name': stop.name,
            'lat': stop.lat,
            'lng': stop.lng,
            'category': stop.stop_category,
            'icon': stop.get_category_icon(),
            'position': stop.position,
            'route_to_next': json.loads(stop.route_to_next) if stop.route_to_next else None,
            'distance_to_next_km': stop.distance_to_next_km,
            'duration_to_next_min': stop.duration_to_next_min,
            'route_type': stop.route_type,
            'photo_url': stop.photo_url or '',
        }
        stop_data.append(sd)
    return render_template('trip_detail.html', trip=trip, stops=stops,
                           stop_data=json.dumps(stop_data), hikes=hikes,
                           packing_items=packing_items)

@app.route('/trip/<int:trip_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    if request.method == 'POST':
        try:
            trip.name = request.form.get('name')
            trip.description = request.form.get('description')
            trip.start_date = request.form.get('start_date') or None
            trip.end_date = request.form.get('end_date') or None
            trip.notes = request.form.get('notes')
            db.session.commit()
            return redirect(url_for('trip_detail', trip_id=trip.id))
        except Exception as e:
            db.session.rollback()
            return render_template('trip_form.html', trip=trip, error=str(e))
    return render_template('trip_form.html', trip=trip)

@app.route('/trip/<int:trip_id>/delete', methods=['POST'])
@login_required
def delete_trip(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    db.session.delete(trip)
    db.session.commit()
    return redirect(url_for('trip_list'))

@app.route('/api/geocode')
def geocode_search():
    """Search for places using Nominatim (OpenStreetMap geocoding)"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded_q}&format=json&limit=5&addressdetails=1&accept-language=de"
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'HikeNTravel/1.0 (hiking trip planner)')
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        results = []
        for item in data:
            results.append({
                'name': item.get('display_name', ''),
                'short_name': item.get('name', item.get('display_name', '')[:40]),
                'lat': float(item.get('lat', 0)),
                'lng': float(item.get('lon', 0)),
                'type': item.get('type', ''),
                'category': item.get('class', '')
            })
        return jsonify(results)
    except Exception as e:
        return jsonify([])

@app.route('/api/trip/<int:trip_id>/stop', methods=['POST'])
@login_required
def add_trip_stop(trip_id):
    trip = Trip.query.get_or_404(trip_id)
    data = request.get_json()
    max_pos = db.session.query(db.func.max(TripStop.position)).filter_by(trip_id=trip.id).scalar() or -1
    stop = TripStop(
        trip_id=trip.id,
        name=data.get('name', 'Neuer Stop'),
        description=data.get('description', ''),
        stop_category=data.get('stop_category', 'sehenswuerdigkeit'),
        lat=float(data.get('lat', 0)),
        lng=float(data.get('lng', 0)),
        position=max_pos + 1,
        duration_minutes=int(data.get('duration_minutes', 0)) or None,
        notes=data.get('notes', ''),
        hike_id=int(data.get('hike_id')) if data.get('hike_id') else None,
        route_type=data.get('route_type', 'car'),
        photo_url=data.get('photo_url', '') or None,
    )
    db.session.add(stop)
    db.session.commit()

    # Auto-route from previous stop
    prev_stop = TripStop.query.filter_by(trip_id=trip.id).filter(TripStop.position < stop.position).order_by(TripStop.position.desc()).first()
    if prev_stop:
        route_result = calculate_route_between(prev_stop, stop)
        if route_result:
            prev_stop.route_to_next = json.dumps(route_result.get('geometry'))
            prev_stop.distance_to_next_km = route_result.get('distance_km')
            prev_stop.duration_to_next_min = route_result.get('duration_min')
            prev_stop.route_type = data.get('route_type', 'car')
            db.session.commit()

    return jsonify({
        'id': stop.id,
        'name': stop.name,
        'lat': stop.lat,
        'lng': stop.lng,
        'position': stop.position,
        'category': stop.stop_category,
        'icon': stop.get_category_icon(),
    })

@app.route('/api/trip/<int:trip_id>/stop/<int:stop_id>', methods=['PUT'])
@login_required
def update_trip_stop(trip_id, stop_id):
    stop = TripStop.query.filter_by(id=stop_id, trip_id=trip_id).first_or_404()
    data = request.get_json()
    stop.name = data.get('name', stop.name)
    stop.description = data.get('description', stop.description)
    stop.stop_category = data.get('stop_category', stop.stop_category)
    stop.lat = float(data.get('lat', stop.lat))
    stop.lng = float(data.get('lng', stop.lng))
    stop.duration_minutes = int(data.get('duration_minutes', 0)) or stop.duration_minutes
    stop.notes = data.get('notes', stop.notes)
    stop.route_type = data.get('route_type', stop.route_type)
    stop.hike_id = int(data.get('hike_id')) if data.get('hike_id') else stop.hike_id
    if 'photo_url' in data:
        stop.photo_url = data.get('photo_url') or None
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/trip/<int:trip_id>/stop/<int:stop_id>', methods=['DELETE'])
@login_required
def delete_trip_stop(trip_id, stop_id):
    stop = TripStop.query.filter_by(id=stop_id, trip_id=trip_id).first_or_404()
    db.session.delete(stop)
    db.session.commit()

    # Recalculate positions
    remaining = TripStop.query.filter_by(trip_id=trip_id).order_by(TripStop.position).all()
    for i, s in enumerate(remaining):
        s.position = i
    db.session.commit()

    recalculate_trip_routes(trip_id)
    return jsonify({'success': True})

@app.route('/api/trip/<int:trip_id>/reorder', methods=['POST'])
@login_required
def reorder_tripStops(trip_id):
    data = request.get_json()
    order = data.get('order', [])
    for i, stop_id in enumerate(order):
        stop = TripStop.query.filter_by(id=stop_id, trip_id=trip_id).first()
        if stop:
            stop.position = i
    db.session.commit()
    recalculate_trip_routes(trip_id)
    return jsonify({'success': True})

@app.route('/api/trip/<int:trip_id>/recalculate-routes', methods=['POST'])
@login_required
def api_recalculate_routes(trip_id):
    recalculate_trip_routes(trip_id)
    stops = TripStop.query.filter_by(trip_id=trip_id).order_by(TripStop.position).all()
    result = []
    for stop in stops:
        result.append({
            'id': stop.id,
            'route_to_next': json.loads(stop.route_to_next) if stop.route_to_next else None,
            'distanceÝ×Û^ÚÛIÎÝÜ\Ý[ÙWÝ×Û^ÚÛK	Ù\][ÛÝ×Û^ÛZ[ÎÝÜ\][ÛÝ×Û^ÛZ[	ÜÝ]WÝ\IÎÝÜÝ]WÝ\KJB]\ÛÛYJÉÜÝÜÉÎ\Ý[JBÈOOOOOOOOOOOOOOOOOOOHPÒÒSÈTÕTHOOOOOOOOOOOOOOOOOOOB\Ý]J	ËØ\KÝ\Ï[\ÚYÜXÚÚ[ÉËY]ÙÏVÉÑÑU	×JBYÙ]ÜXÚÚ[×Ú][\Ê\ÚY
N][\ÈHXÚÚ[Ò][K]Y\K[\ØJ\ÚY]\ÚY
KÜ\ØJXÚÚ[Ò][KØ]YÛÜKXÚÚ[Ò][KY
K[

B]\ÛÛYJÞÂ	ÚY	Î][KY	Û[YIÎ][K[YK	Ú\×ÜXÚÙY	Î][K\×ÜXÚÙY	ØØ]YÛÜIÎ][KØ]YÛÜKHÜ][H[][\×JB\Ý]J	ËØ\KÝ\Ï[\ÚYÜXÚÚ[ÉËY]ÙÏVÉÔÔÕ	×JBÙÚ[Ü\]Z\YYYÜXÚÚ[×Ú][J\ÚY
N\H\]Y\KÙ]ÛÜÍ
\ÚY
B]HH\]Y\ÝÙ]ÚÛÛ
B[YHH]KÙ]
	Û[YIË	ÉÊKÝ\

BYÝ[YN]\ÛÛYJÉÙ\ÜÎ	Ó[YH\Ü\XÚ	ßJK
][HHXÚÚ[Ò][J\ÚY]\Y[YO[[YK\×ÜXÚÙYQ[ÙKØ]YÛÜOY]KÙ]
	ØØ]YÛÜIË	ÔÛÛÝYÙ\ÉÊK
BÙ\ÜÚ[ÛY
][JBÙ\ÜÚ[ÛÛÛ[Z]

B]\ÛÛYJÉÚY	Î][KY	Û[YIÎ][K[YK	Ú\×ÜXÚÙY	Î][K\×ÜXÚÙY	ØØ]YÛÜIÎ][KØ]YÛÜ_JB\Ý]J	ËØ\KÝ\Ï[\ÚYÜXÚÚ[ËÏ[][WÚYËY]ÙÏVÉÔU	×JBÙÚ[Ü\]Z\YY\]WÜXÚÚ[×Ú][J\ÚY][WÚY
N][HHXÚÚ[Ò][K]Y\K[\ØJYZ][WÚY\ÚY]\ÚY
K\ÝÛÜÍ

B]HH\]Y\ÝÙ]ÚÛÛ
BY	Û[YIÈ[]N][K[YHH]VÉÛ[YI×BY	Ú\×ÜXÚÙY	È[]N][K\×ÜXÚÙYHÛÛ
]VÉÚ\×ÜXÚÙY	×JBY	ØØ]YÛÜIÈ[]N][KØ]YÛÜHH]VÉØØ]YÛÜI×BÙ\ÜÚ[ÛÛÛ[Z]

B]\ÛÛYJÉÜÝXØÙ\ÜÉÎY_JB\Ý]J	ËØ\KÝ\Ï[\ÚYÜXÚÚ[ËÏ[][WÚYËY]ÙÏVÉÑSUI×JBÙÚ[Ü\]Z\YY[]WÜXÚÚ[×Ú][J\ÚY][WÚY
N][HHXÚÚ[Ò][K]Y\K[\ØJYZ][WÚY\ÚY]\ÚY
K\ÝÛÜÍ

BÙ\ÜÚ[Û[]J][JBÙ\ÜÚ[ÛÛÛ[Z]

B]\ÛÛYJÉÜÝXØÙ\ÜÉÎY_JBÈOOOOOOOOOOOOOOOOOOOHÕUHSTÈOOOOOOOOOOOOOOOOOOOBYXØ[Ý[]WÝ\ÜÝ]\Ê\ÚY
NÝÜÈH\ÝÜ]Y\K[\ØJ\ÚY]\ÚY
KÜ\ØJ\ÝÜÜÚ][ÛK[

BÜH[[ÙJ[ÝÜÊJNYH[ÝÜÊHHNÝ]WÜ\Ý[HØ[Ý[]WÜÝ]WØ]ÙY[ÝÜÖÚWKÝÜÖÚH
ÈWJBYÝ]WÜ\Ý[ÝÜÖÚWKÝ]WÝ×Û^HÛÛ[\ÊÝ]WÜ\Ý[Ù]
	ÙÙ[ÛY]IÊJBÝÜÖÚWK\Ý[ÙWÝ×Û^ÚÛHHÝ]WÜ\Ý[Ù]
	Ù\Ý[ÙWÚÛIÊBÝÜÖÚWK\][ÛÝ×Û^ÛZ[HÝ]WÜ\Ý[Ù]
	Ù\][ÛÛZ[ÊB[ÙNÝÜÖÚWKÝ]WÝ×Û^HÛBÝÜÖÚWK\Ý[ÙWÝ×Û^ÚÛHHÛBÝÜÖÚWK\][ÛÝ×Û^ÛZ[HÛB[ÙNÝÜÖÚWKÝ]WÝ×Û^HÛBÝÜÖÚWK\Ý[ÙWÝ×Û^ÚÛHHÛBÝÜÖÚWK\][ÛÝ×Û^ÛZ[HÛBÙ\ÜÚ[ÛÛÛ[Z]

BYØ[Ý[]WÜÝ]WØ]ÙY[ÝÜØKÝÜØNN\WÚÙ^HH\ÛÛYËÙ]
	ÓPTWÐTWÒÑVIË	ÉÊBÝ]WÝ\HHÝÜØKÝ]WÝ\HÜ	ØØ\ÂYÝ]WÝ\HOH	ÜXX×Ý[ÜÜ	ÎÝ]WÝ\HH	ØØ\ÂÝ]WØ\WÝ\H
ÎËØ\KX\KÞÝKÜÝ][ËÜÝ]HØ\ZÙ^OH
È\WÚÙ^H
Â[ÏYHÝ\H
ÈÝÝÜØKÊH
È
ÈÝÝÜØK]
H
Â[H
ÈÝÝÜØÊH
È
ÈÝÝÜØ]
H
ÂÝ]U\OH
ÈÝ]WÝ\B
B\HH\X\]Y\Ý\]Y\Ý
Ý]WØ\WÝ\
B\KYÚXY\	Õ\Ù\PYÙ[	Ë	ÒZÙS][ÌK	ÊB\KYÚXY\	ÐXØÙ\	Ë	Ø\XØ][ÛÚÛÛÊB\ÜH\X\]Y\Ý\Ü[\K[Y[Ý]LMJBÝ]WÙ]HHÛÛØYÊ\ÜXY

KXÛÙJ	Ý]N	ÊJB\Ý[ÙWÛHHÝ]WÙ]KÙ]
	Û[Ý	Ë
B\][ÛÜÈHÝ]WÙ]KÙ]
	Ù\][ÛË
BÙ[×ÙX]\HHÝ]WÙ]KÙ]
	ÙÙ[ÛY]IËßJBY\Ú[Ý[ÙJÙ[×ÙX]\KXÝ
H[	ÙÙ[ÛY]IÈ[Ù[×ÙX]\NÙ[ÛY]HHÙ[×ÙX]\VÉÙÙ[ÛY]I×B[ÙNÙ[ÛY]HHÙ[×ÙX]\B]\Â	ÙÙ[ÛY]IÎÙ[ÛY]K	Ù\Ý[ÙWÚÛIÎÝ[
\Ý[ÙWÛHÈLJHY\Ý[ÙWÛHL[ÙHÝ[
\Ý[ÙWÛKJK	Ù\][ÛÛZ[Î[
\][ÛÜÈÈ

HY\][ÛÜÈL[ÙH[
\][ÛÜÊKB^Ù\^Ù\[Û]\ÛBÈOOOOOOOOOOOOOOOOOOOHPTHÕUHTHOOOOOOOOOOOOOOOOOOOBYXÛÙWÛX\WÜÊ×ÜÝ[ÊNSPUH	ÌPÑQÒ
RÓSÔTÕUÖVLXXÙÙYÚ
ZZÛ[ÛÜ\Ý]]Þ^ÂUWÐÒTÈH
QWÐÒTÈHH
Y\ÙWÛ[X\\ÛÝ[
N\Ý[HHHÛÝ[Ú[HHYÝ\Z\ÙH[YQ\ÜÈ]HBÚH\Ü

B[^HSPU[
Ú
BY[^OHLNÛÛ[YB\Ý[H
\Ý[
H
È[^HOHB]\\Ý[\Ý[ÈH×BÛÛÜÈHÌBÛÛÜÚ[^H\H\Ý
]\ÙY
×ÜÝ[ËÝ\

JJBÚ[H\[HH\ÙWÛ[X\\JBY
[H	UWÐÒTÊHOHUWÐÒTÎ[HOHUWÐÒTÂ[HH

[H	MJH
H
È\ÙWÛ[X\\
BÛÛÜÖØÛÛÜÚ[^HH[B[Y
[H	QWÐÒTÊHOHQWÐÒTÎ[HH

[H	MJHLH
È\ÙWÛ[X\\B[HOHHMBÛÛÜÖØÛÛÜÚ[^H
ÏH[B[ÙN[HH

[H	ÌJH
H
È\ÙWÛ[X\\JB[HOHHLÛÛÜÖØÛÛÜÚ[^H
ÏH[BYÛÛÜÚ[^ÈHÛÛÜÖÌH
ÍÈ
H
HHN]HÛÛÜÖÌWH
NÈ
H
HHL\Ý[Ë\[
ÉÛ]	ÎÝ[
]
K	ÛÉÎÝ[
Ë
_JBÛÛÜÚ[^H
ÛÛÜÚ[^
ÈJH	H]\\Ý[Â\Ý]J	ËØ\KÙ]Ú[X\K\Ý]IËY]ÙÏVÉÔÔÕ	×JBY]ÚÛX\WÜÝ]J
N]HH\]Y\ÝÙ]ÚÛÛ
BX\WÝ\H]KÙ]
	Ý\	Ë	ÉÊBN\ÛÛYÝ\HX\WÝ\Y	ËÜËÉÈ[X\WÝ\N\HH\X\]Y\Ý\]Y\Ý
X\WÝ\Y]ÙIÒPQ	ÊB\KYÚXY\	Õ\Ù\PYÙ[	Ë	Ó[Þ[KÍK
Ú[ÝÜÈLÈÚ[È

H\UÙXÚ]ÍLÍËÍ
ÒSZÙHÙXÚÛÊHÚÛYKÌLØY\KÍLÍËÍÊB\KYÚXY\	ÐXØÙ\	Ë	Ý^Ú[	ÊB\ÜÛÙHH\X\]Y\Ý\Ü[\K[Y[Ý]LL
B\ÛÛYÝ\H\ÜÛÙK\^Ù\^Ù\[ÛN\HH\X\]Y\Ý\]Y\Ý
X\WÝ\
B\KYÚXY\	Õ\Ù\PYÙ[	Ë	Ó[Þ[KÍK
Ú[ÝÜÈLÈÚ[È

H\UÙXÚ]ÍLÍËÍ
ÒSZÙHÙXÚÛÊHÚÛYKÌLØY\KÍLÍËÍÊB\KYÚXY\	ÐXØÙ\	Ë	Ý^Ú[	ÊB\ÜÛÙHH\X\]Y\Ý\Ü[\K[Y[Ý]LL
B\ÛÛYÝ\H\ÜÛÙK\Y\ÛÛYÝ\OHX\WÝ\Ü	ËÜËÉÈ[\ÛÛYÝ\[\ÜB[H\ÜÛÙKXY

KXÛÙJ	Ý]N	Ë\ÜÏIÚYÛÜIÊBY]WÛX]ÚHKÙX\Ú
Ý\J×	Ï×JÊIË[KQÓÔPÐTÑJBYY]WÛX]Ú\ÛÛYÝ\HY]WÛX]ÚÜÝ\
JB^Ù\^Ù\[Û\ÛÛYÝ\HX\WÝ\\ÙYH\X\ÙK\\ÙJ\ÛÛYÝ\
B\[\ÈH\X\ÙK\ÙWÜ\Ê\ÙY]Y\JBÝ\Û]HÛBÝ\ÛÈHÛB[Û]HÛB[ÛÈHÛB×Ý[Y\ÈH\[\ËÙ]
	ÜÉË×JBY×Ý[Y\È[×Ý[Y\ÖÌNNØ^\Ú[ÈHXÛÙWÛX\WÜÊ×Ý[Y\ÖÌJBY[Ø^\Ú[ÊHHNÝ\Û]HØ^\Ú[ÖÌVÉÛ]	×BÝ\ÛÈHØ^\Ú[ÖÌVÉÛÉ×BY[Ø^\Ú[ÊHH[Û]HØ^\Ú[ÖËLWVÉÛ]	×B[ÛÈHØ^\Ú[ÖËLWVÉÛÉ×B^Ù\^Ù\[Û\ÜÂYÝÝ\Û][	Þ	È[\[\È[	ÞIÈ[\[\ÎÙ[\ÛÈHØ]
\[\ÖÉÞ	×VÌJBÙ[\Û]HØ]
\[\ÖÉÞI×VÌJBÝ\Û]HÙ[\Û]Ý\ÛÈHÙ[\ÛÂ[WÝ[YHH\[\ËÙ]
	Ù[IËÓÛWJVÌBYÝÝ\Û][[WÝ[YN]\ÛÛYJÂ	Ü\ÛÛYÝ\	Î\ÛÛYÝ\	Ù\ÜÎ	ÑY\Ù\[ÈZYÝZ[[Ø[\Y
ÙZ[Ý][[KÛÈ[Ý[ÛY\\ÎJHÙYH[Y]YX\KÛÛHHÛXÚÙHØ[XÚÈ]YÝ]HÊH[HZ[HÝ]H[[È\ÈYÈ
HÛÜY\HYH]YHT[YYÙHÚYHY\Z[ÂJK
YÝÝ\Û]ÜÝÝ\ÛÎ]\ÛÛYJÉÙ\ÜÎ	ÒÛÛHÙZ[HÛÛÜ[][]\È[H[È^ZY\[]H\Ù[HZ[HÛHX\KÛÛHÝ]KUTË	Ü\ÛÛYÝ\	Î\ÛÛYÝ\JK
YÝ[Û]ÜÝ[ÛÎ]\ÛÛYJÂ	ÜÝ\Û]	ÎÝ[
Ý\Û]
K	ÜÝ\ÛÉÎÝ[
Ý\ÛË
K	Ü\ÛÛYÝ\	Î\ÛÛYÝ\	Ù\ÜÎ	Ó\Ý\[ÝÙY[[]HÚX[[[ÝX[Y[Z[ÂJK
\WÚÙ^HH\ÛÛYËÙ]
	ÓPTWÐTWÒÑVIË	ÉÊBÝ]WØ\WÝ\H
ÎËØ\KX\KÞÝKÜÝ][ËÜÝ]HØ\ZÙ^OH
È\WÚÙ^H
Â[ÏYHÝ\H
ÈÝÝ\ÛÊH
È
ÈÝÝ\Û]
H
Â[H
ÈÝ[ÛÊH
È
ÈÝ[Û]
H
ÂÝ]U\OYÛÝÚZÚ[È
B\HH\X\]Y\Ý\]Y\Ý
Ý]WØ\WÝ\
B\KYÚXY\	Õ\Ù\PYÙ[	Ë	ÒZÙS][ÌK	ÊB\KYÚXY\	ÐXØÙ\	Ë	Ø\XØ][ÛÚÛÛÊB\ÜH\X\]Y\Ý\Ü[\K[Y[Ý]LMJBÝ]WÙ]HHÛÛØYÊ\ÜXY

KXÛÙJ	Ý]N	ÊJB\Ý[ÙWÛHHÝ]WÙ]KÙ]
	Û[Ý	Ë
B\][ÛÜÈHÝ]WÙ]KÙ]
	Ù\][ÛË
BÙ[×ÙX]\HHÝ]WÙ]KÙ]
	ÙÙ[ÛY]IËßJBY\Ú[Ý[ÙJÙ[×ÙX]\KXÝ
H[	ÙÙ[ÛY]IÈ[Ù[×ÙX]\NÙ[ÛY]HHÙ[×ÙX]\VÉÙÙ[ÛY]I×B[ÙNÙ[ÛY]HHÙ[×ÙX]\B[]][ÛÙØZ[H[]][ÛÛÜÜÈHNÝ]WØÛÛÜÈH×BY\Ú[Ý[ÙJÙ[ÛY]KXÝ
H[Ù[ÛY]KÙ]
	Ý\IÊHOH	Ó[TÝ[ÉÎÝ]WØÛÛÜÈHÙ[ÛY]KÙ]
	ØÛÛÜ[]\ÉË×JBYÝ]WØÛÛÜÎX^ÜÚ[ÈHMY[Ý]WØÛÛÜÊHX^ÜÚ[ÎÝ\H[Ý]WØÛÛÜÊHÈX^ÜÚ[ÂØ[\YHÜÝ]WØÛÛÜÖÚ[
H
Ý\
WHÜH[[ÙJX^ÜÚ[ÊWB[ÙNØ[\YHÝ]WØÛÛÜÂÜÚ][ÛÈH	ÎÉËÚ[	ÞßKßIËÜX]
Ý[
ÖÌK
KÝ[
ÖÌWK
JBÜÈ[Ø[\Y
B[]Ý\H
	ÚÎËØ\KX\KÞÝKÙ[]][ÛÂ	ÏØ\ZÙ^OIÈ
È\WÚÙ^H
Â	ÉÜÚ][ÛÏIÈ
ÈÜÚ][ÛÂ
B[]Ü\HH\X\]Y\Ý\]Y\Ý
[]Ý\
B[]Ü\KYÚXY\	Õ\Ù\PYÙ[	Ë	ÒZÙS][ÌK	ÊB[]Ü\KYÚXY\	ÐXØÙ\	Ë	Ø\XØ][ÛÚÛÛÊB[]Ü\ÜH\X\]Y\Ý\Ü[[]Ü\K[Y[Ý]LMJB[]Ù]HHÛÛØYÊ[]Ü\ÜXY

KXÛÙJ	Ý]N	ÊJB[]][ÛÈHÚ][VÉÙ[]][Û×HÜ][H[[]Ù]KÙ]
	Ú][\ÉË×JWBY[[]][ÛÊHNÜH[[ÙJK[[]][ÛÊJNYH[]][ÛÖÚWHH[]][ÛÖÚHHWBYY[]][ÛÙØZ[
ÏHY[ÙN[]][ÛÛÜÜÈ
ÏHXÊYB[]][ÛÙØZ[H[
Ý[
[]][ÛÙØZ[JB[]][ÛÛÜÜÈH[
Ý[
[]][ÛÛÜÜÊJB^Ù\^Ù\[Û\ÜÂ\Ý[ÙWÚÛHHÝ[
\Ý[ÙWÛHÈLJHY\Ý[ÙWÛHL[ÙHÝ[
\Ý[ÙWÛKJB\][ÛÛZ[]\ÈH[
\][ÛÜÈÈ

HY\][ÛÜÈL[ÙH[
\][ÛÜÊB]\ÛÛYJÂ	Ù\Ý[ÙWÚÛIÎ\Ý[ÙWÚÛK	Ù\][ÛÛZ[]\ÉÎ\][ÛÛZ[]\Ë	Ù[]][ÛÙØZ[Î[]][ÛÙØZ[	Ù[]][ÛÛÜÜÉÎ[]][ÛÛÜÜË	ÜÝ\Û]	ÎÝ[
Ý\Û]
K	ÜÝ\ÛÉÎÝ[
Ý\ÛË
K	Ù[Û]	ÎÝ[
[Û]
K	Ù[ÛÉÎÝ[
[ÛË
K	ÜÝ]WÙÙ[ÛY]IÎÛÛ[\ÊÙ[ÛY]JK	Ü\ÛÛYÝ\	Î\ÛÛYÝ\JB^Ù\^Ù\[Û\ÈN]\ÛÛYJÉÙ\ÜÎ	ÑZ\	È
ÈÝJ_JK
LY×Û[YW×ÈOH	××ÛXZ[×ÉÎ\[XYÏUYJB
