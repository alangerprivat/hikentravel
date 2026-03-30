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
        columns_to_add = [
            ('route_geometry', 'TEXT'),
            ('mapy_url', 'VARCHAR(500)'),
        ]
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(db.text(f"SELECT {col_name} FROM hike LIMIT 1"))
            except Exception:
                conn.rollback()
                try:
                    conn.execute(db.text(f"ALTER TABLE hike ADD COLUMN {col_name} {col_type}"))
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
                'id': h.id, 'name': h.name, 'region': h.region,
                'distance_km': h.distance_km, 'elevation_gain': h.elevation_gain,
                'difficulty': h.difficulty, 'duration_minutes': h.duration_minutes,
                'category': h.category.name if h.category else None,
                'start_lat': h.start_lat, 'start_lng': h.start_lng,
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
            'id': h.id, 'name': h.name,
            'lat': h.start_lat, 'lng': h.start_lng,
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
        }
        stop_data.append(sd)

    return render_template('trip_detail.html', trip=trip, stops=stops,
                           stop_data=json.dumps(stop_data), hikes=hikes)


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
    stop.hike_id = int(data.get('hike_id')) if data.get('hike_id') else stop.hike_id
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
    # Recalculate route for the stop now before the deleted one
    recalculate_trip_routes(trip_id)
    return jsonify({'success': True})


@app.route('/api/trip/<int:trip_id>/reorder', methods=['POST'])
@login_required
def reorder_trip_stops(trip_id):
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
            'distance_to_next_km': stop.distance_to_next_km,
            'duration_to_next_min': stop.duration_to_next_min,
            'route_type': stop.route_type,
        })
    return jsonify({'stops': result})


def recalculate_trip_routes(trip_id):
    stops = TripStop.query.filter_by(trip_id=trip_id).order_by(TripStop.position).all()
    for i in range(len(stops)):
        if i < len(stops) - 1:
            route_result = calculate_route_between(stops[i], stops[i + 1])
            if route_result:
                stops[i].route_to_next = json.dumps(route_result.get('geometry'))
                stops[i].distance_to_next_km = route_result.get('distance_km')
                stops[i].duration_to_next_min = route_result.get('duration_min')
            else:
                stops[i].route_to_next = None
                stops[i].distance_to_next_km = None
                stops[i].duration_to_next_min = None
        else:
            stops[i].route_to_next = None
            stops[i].distance_to_next_km = None
            stops[i].duration_to_next_min = None
    db.session.commit()


def calculate_route_between(stop_a, stop_b):
    try:
        api_key = app.config.get('MAPY_API_KEY', '')
        route_type = stop_a.route_type or 'car'
        if route_type == 'public_transport':
            route_type = 'car'
        route_api_url = (
            "https://api.mapy.cz/v1/routing/route"
            "?apikey=" + api_key +
            "&lang=de"
            "&start=" + str(stop_a.lng) + "," + str(stop_a.lat) +
            "&end=" + str(stop_b.lng) + "," + str(stop_b.lat) +
            "&routeType=" + route_type
        )
        req = urllib.request.Request(route_api_url)
        req.add_header('User-Agent', 'HikeNTravel/1.0')
        req.add_header('Accept', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        route_data = json.loads(resp.read().decode('utf-8'))

        distance_m = route_data.get('length', 0)
        duration_s = route_data.get('duration', 0)
        geo_feature = route_data.get('geometry', {})
        if isinstance(geo_feature, dict) and 'geometry' in geo_feature:
            geometry = geo_feature['geometry']
        else:
            geometry = geo_feature

        return {
            'geometry': geometry,
            'distance_km': round(distance_m / 1000, 1) if distance_m > 100 else round(distance_m, 1),
            'duration_min': int(duration_s / 60) if duration_s > 100 else int(duration_s),
        }
    except Exception:
        return None


# ==================== MAPY ROUTE API ====================

def decode_mapy_rc(rc_string):
    ALPHABET = '0ABCD2EFGH4IJKLMN6OPQRST8UVWXYZ-1abcd3efgh5ijklmn7opqrst9uvwxyz.'
    FIVE_CHARS = 2 << 4
    THREE_CHARS = 1 << 4

    def parse_number(arr, count):
        result = 0
        i = count
        while i > 0:
            if not arr:
                raise ValueError("No data")
            ch = arr.pop()
            index = ALPHABET.find(ch)
            if index == -1:
                continue
            result = (result << 6) + index
            i -= 1
        return result

    results = []
    coords = [0, 0]
    coord_index = 0
    arr = list(reversed(rc_string.strip()))

    while arr:
        num = parse_number(arr, 1)
        if (num & FIVE_CHARS) == FIVE_CHARS:
            num -= FIVE_CHARS
            num = ((num & 15) << 24) + parse_number(arr, 4)
            coords[coord_index] = num
        elif (num & THREE_CHARS) == THREE_CHARS:
            num = ((num & 15) << 12) + parse_number(arr, 2)
            num -= 1 << 15
            coords[coord_index] += num
        else:
            num = ((num & 31) << 6) + parse_number(arr, 1)
            num -= 1 << 10
            coords[coord_index] += num
        if coord_index:
            lng = coords[0] * 360 / (1 << 28) - 180
            lat = coords[1] * 180 / (1 << 28) - 90
            results.append({'lat': round(lat, 6), 'lng': round(lng, 6)})
        coord_index = (coord_index + 1) % 2
    return results


@app.route('/api/fetch-mapy-route', methods=['POST'])
def fetch_mapy_route():
    data = request.get_json()
    mapy_url = data.get('url', '')
    try:
        resolved_url = mapy_url
        if '/s/' in mapy_url:
            try:
                req = urllib.request.Request(mapy_url, method='HEAD')
                req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                req.add_header('Accept', 'text/html')
                response = urllib.request.urlopen(req, timeout=10)
                resolved_url = response.url
            except Exception:
                try:
                    req = urllib.request.Request(mapy_url)
                    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                    req.add_header('Accept', 'text/html')
                    response = urllib.request.urlopen(req, timeout=10)
                    resolved_url = response.url
                    if resolved_url == mapy_url or '/s/' in resolved_url:
                        import re
                        html = response.read().decode('utf-8', errors='ignore')
                        meta_match = re.search(r'url=([^"\'>\s]+)', html, re.IGNORECASE)
                        if meta_match:
                            resolved_url = meta_match.group(1)
                except Exception:
                    resolved_url = mapy_url

        parsed = urllib.parse.urlparse(resolved_url)
        params = urllib.parse.parse_qs(parsed.query)
        start_lat = None
        start_lng = None
        end_lat = None
        end_lng = None

        rc_values = params.get('rc', [])
        if rc_values and rc_values[0]:
            try:
                waypoints = decode_mapy_rc(rc_values[0])
                if len(waypoints) >= 1:
                    start_lat = waypoints[0]['lat']
                    start_lng = waypoints[0]['lng']
                if len(waypoints) >= 2:
                    end_lat = waypoints[-1]['lat']
                    end_lng = waypoints[-1]['lng']
            except Exception:
                pass

        if not start_lat and 'x' in params and 'y' in params:
            center_lng = float(params['x'][0])
            center_lat = float(params['y'][0])
            start_lat = center_lat
            start_lng = center_lng

        dim_value = params.get('dim', [None])[0]
        if not start_lat and dim_value:
            return jsonify({
                'resolved_url': resolved_url,
                'error': 'Dieser Link zeigt einen Wanderpfad (kein Routenplan). So funktioniert es: 1) Oeffne den Pfad auf mapy.com 2) Klicke oben rechts auf Route 3) Plane eine Route entlang des Pfads 4) Kopiere die neue URL und fuege sie hier ein.'
            }), 400

        if not start_lat or not start_lng:
            return jsonify({'error': 'Konnte keine Koordinaten aus dem Link extrahieren. Bitte verwende eine volle Mapy.com Route-URL.',
                            'resolved_url': resolved_url}), 400

        if not end_lat or not end_lng:
            return jsonify({
                'start_lat': round(start_lat, 6),
                'start_lng': round(start_lng, 6),
                'resolved_url': resolved_url,
                'error': 'Nur Startpunkt gefunden. Bitte gib den Endpunkt manuell ein.'
            }), 400

        api_key = app.config.get('MAPY_API_KEY', '')
        route_api_url = (
            "https://api.mapy.cz/v1/routing/route"
            "?apikey=" + api_key +
            "&lang=de"
            "&start=" + str(start_lng) + "," + str(start_lat) +
            "&end=" + str(end_lng) + "," + str(end_lat) +
            "&routeType=foot_hiking"
        )
        req = urllib.request.Request(route_api_url)
        req.add_header('User-Agent', 'HikeNTravel/1.0')
        req.add_header('Accept', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        route_data = json.loads(resp.read().decode('utf-8'))

        distance_m = route_data.get('length', 0)
        duration_s = route_data.get('duration', 0)
        geo_feature = route_data.get('geometry', {})
        if isinstance(geo_feature, dict) and 'geometry' in geo_feature:
            geometry = geo_feature['geometry']
        else:
            geometry = geo_feature

        elevation_gain = 0
        elevation_loss = 0
        try:
            route_coords = []
            if isinstance(geometry, dict) and geometry.get('type') == 'LineString':
                route_coords = geometry.get('coordinates', [])
            if route_coords:
                max_points = 256
                if len(route_coords) > max_points:
                    step = len(route_coords) / max_points
                    sampled = [route_coords[int(i * step)] for i in range(max_points)]
                else:
                    sampled = route_coords
                positions = ';'.join(
                    '{},{}'.format(round(c[0], 6), round(c[1], 6)) for c in sampled
                )
                elev_url = (
                    'https://api.mapy.cz/v1/elevation'
                    '?apikey=' + api_key +
                    '&positions=' + positions
                )
                elev_req = urllib.request.Request(elev_url)
                elev_req.add_header('User-Agent', 'HikeNTravel/1.0')
                elev_req.add_header('Accept', 'application/json')
                elev_resp = urllib.request.urlopen(elev_req, timeout=15)
                elev_data = json.loads(elev_resp.read().decode('utf-8'))
                elevations = [item['elevation'] for item in elev_data.get('items', [])]
                if len(elevations) > 1:
                    for i in range(1, len(elevations)):
                        diff = elevations[i] - elevations[i - 1]
                        if diff > 0:
                            elevation_gain += diff
                        else:
                            elevation_loss += abs(diff)
                    elevation_gain = int(round(elevation_gain))
                    elevation_loss = int(round(elevation_loss))
        except Exception:
            pass

        distance_km = round(distance_m / 1000, 1) if distance_m > 100 else round(distance_m, 1)
        duration_minutes = int(duration_s / 60) if duration_s > 100 else int(duration_s)

        return jsonify({
            'distance_km': distance_km,
            'duration_minutes': duration_minutes,
            'elevation_gain': elevation_gain,
            'elevation_loss': elevation_loss,
            'start_lat': round(start_lat, 6),
            'start_lng': round(start_lng, 6),
            'end_lat': round(end_lat, 6),
            'end_lng': round(end_lng, 6),
            'route_geometry': json.dumps(geometry),
            'resolved_url': resolved_url
        })
    except Exception as e:
        return jsonify({'error': 'Fehler: ' + str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
