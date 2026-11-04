from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
import json

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# ── CLOUDINARY CONFIG ────────────────────────────────
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'

# ── MODELS ──────────────────────────────────────────
class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False)
    images = db.Column(db.Text, nullable=True)

    def get_images(self):
        if self.images:
            try:
                return json.loads(self.images)
            except Exception:
                return []
        return []

    def get_first_image(self):
        images = self.get_images()
        return images[0] if images else None

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# ── DATABASE MIGRATION ───────────────────────────────
def run_migrations():
    from sqlalchemy import text, inspect
    try:
        inspector = inspect(db.engine)

        # Check if product table exists
        if 'product' not in inspector.get_table_names():
            print("⚠️ Product table not found, skipping migration")
            return

        columns = [col['name'] for col in inspector.get_columns('product')]

        with db.engine.connect() as conn:
            # Add images column if it doesn't exist
            if 'images' not in columns:
                try:
                    conn.execute(text("ALTER TABLE product ADD COLUMN images TEXT"))
                    conn.commit()
                    print("✅ Added images column")
                except Exception as e:
                    print(f"⚠️ Could not add images column: {e}")

            # Migrate old image data to images JSON format
            if 'image' in columns:
                try:
                    conn.execute(text("""
                        UPDATE product
                        SET images = '["' || image || '"]'
                        WHERE image IS NOT NULL
                        AND (images IS NULL OR images = '')
                    """))
                    conn.commit()
                    print("✅ Migrated old image data")
                except Exception as e:
                    print(f"⚠️ Could not migrate image data: {e}")

                # Drop old image column
                try:
                    conn.execute(text("ALTER TABLE product DROP COLUMN image"))
                    conn.commit()
                    print("✅ Dropped old image column")
                except Exception as e:
                    print(f"⚠️ Could not drop old image column: {e}")

    except Exception as e:
        print(f"⚠️ Migration error: {e}")

# ── STARTUP ──────────────────────────────────────────
def initialize_app():
    with app.app_context():
        db.create_all()
        run_migrations()

        if not Admin.query.first():
            default_admin = Admin(
                username='admin',
                password=generate_password_hash('bigab2024')
            )
            db.session.add(default_admin)
            db.session.commit()
            print('✅ Default admin created: username=admin password=bigab2024')

# Run on every startup including gunicorn
initialize_app()

# ── ROUTES ──────────────────────────────────────────
@app.route('/')
def home():
    categories = [
        'Jalabiya', 'Senators', 'Kaftans', 'Street Wears',
        'Owanbe Caps', 'Hausa Caps', '2 Piece Male',
        '2 Piece Female', 'Stone Work & Embellishment'
    ]
    highlights = {}
    for cat in categories:
        products = Product.query.filter_by(category=cat).limit(2).all()
        if products:
            highlights[cat] = products
    return render_template('index.html', highlights=highlights)

@app.route('/shop')
def shop():
    category = request.args.get('category', 'All')
    if category == 'All':
        products = Product.query.all()
    else:
        products = Product.query.filter_by(category=category).all()
    return render_template('shop.html', products=products, active_category=category)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid username or password')
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    products = Product.query.all()
    return render_template('admin/dashboard.html', products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        description = request.form['description']
        category = request.form['category']
        images = request.files.getlist('images')

        image_urls = []
        for image in images:
            if image and image.filename != '':
                upload_result = cloudinary.uploader.upload(
                    image,
                    folder='bigab_fashion',
                    transformation=[
                        {'width': 800, 'height': 1000, 'crop': 'fill'},
                        {'quality': 'auto'},
                        {'fetch_format': 'auto'}
                    ]
                )
                image_urls.append(upload_result['secure_url'])

        product = Product(
            name=name,
            price=float(price),
            description=description,
            category=category,
            images=json.dumps(image_urls)
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/add_product.html')

@app.route('/admin/delete_product/<int:id>')
@login_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

# ── RUN ──────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)