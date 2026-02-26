from flask import Flask, render_template, request, flash, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps
import os
import json
from datetime import datetime
from PIL import Image

from models import db, User, Category, Product, Order
from config import Config

# -------------------------------------------------
# APP SETUP
# -------------------------------------------------

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# -------------------------------------------------
# TEMPLATE FILTER
# -------------------------------------------------

@app.template_filter('from_json')
def from_json_filter(data):
    return json.loads(data) if data else []


# -------------------------------------------------
# LOGIN MANAGER
# -------------------------------------------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -------------------------------------------------
# DATABASE INITIALIZATION (Flask 3 Compatible)
# -------------------------------------------------

def initialize_database():
    with app.app_context():
        db.create_all()

        default_categories = [
            {"name": "New Products", "is_special": True},
            {"name": "Hot Products", "is_special": True},
            {"name": "Phones", "is_special": False},
            {"name": "Laptops", "is_special": False},
        ]

        for cat_data in default_categories:
            if not Category.query.filter_by(name=cat_data["name"]).first():
                db.session.add(
                    Category(
                        name=cat_data["name"],
                        is_special=cat_data["is_special"]
                    )
                )

        db.session.commit()


# Create upload folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'thumbnails'), exist_ok=True)

initialize_database()


# -------------------------------------------------
# ADMIN DECORATOR (FIXED)
# -------------------------------------------------

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Admin access required', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------
# PUBLIC ROUTES
# -------------------------------------------------

@app.route('/')
def index():
    products = Product.query.filter_by(is_new=True).limit(8).all()
    hot_products = Product.query.filter_by(is_hot=True).limit(8).all()
    return render_template('index.html', products=products, hot_products=hot_products)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('register.html')

        user = User(
            first_name=request.form['first_name'],
            last_name=request.form['last_name'],
            email=email,
            phone=request.form['phone']
        )

        user.set_password(request.form['password'])

        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Await admin confirmation.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()

        if user and user.check_password(request.form['password']):
            if not user.is_confirmed and not user.is_admin:
                flash('Account not confirmed by admin yet.', 'warning')
                return render_template('login.html')

            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))

        flash('Invalid credentials', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():

    if not current_user.is_confirmed and not current_user.is_admin:
        flash('Account not confirmed by admin.', 'warning')
        return render_template('dashboard.html', unconfirmed=True)

    query = request.args.get('q', '')
    category_id = request.args.get('category')
    sort = request.args.get('sort', 'newest')

    products_query = Product.query

    if query:
        products_query = products_query.filter(Product.name.contains(query))

    if category_id:
        products_query = products_query.filter(Product.category_id == int(category_id))

    if sort == 'price_low':
        products_query = products_query.order_by(Product.price.asc())
    elif sort == 'price_high':
        products_query = products_query.order_by(Product.price.desc())
    else:
        products_query = products_query.order_by(Product.created_at.desc())

    products = products_query.paginate(per_page=12, error_out=False)
    categories = Category.query.filter_by(is_special=False).all()

    return render_template(
        'dashboard.html',
        products=products,
        categories=categories,
        query=query,
        category_id=category_id,
        sort=sort
    )


# -------------------------------------------------
# PRODUCT & ORDER
# -------------------------------------------------

@app.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    if not current_user.is_confirmed and not current_user.is_admin:
        flash('Account not confirmed.', 'warning')
        return redirect(url_for('dashboard'))

    product = Product.query.get_or_404(product_id)

    # Ensure photos is a Python list for the template
    photos = json.loads(product.photos) if product.photos else []

    # Optional: fetch related products (exclude current)
    related_products = Product.query.filter(Product.id != product.id).limit(4).all()

    return render_template('product.html', product=product, photos=photos, products=related_products)


@app.route('/order/<int:product_id>', methods=['GET', 'POST'])
@login_required
def place_order(product_id):

    if not current_user.is_confirmed:
        flash('Account must be confirmed to place orders.', 'warning')
        return redirect(url_for('dashboard'))

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        delivery_date = datetime.strptime(
            request.form['delivery_date'],
            '%Y-%m-%dT%H:%M'
        )

        order = Order(
            user_id=current_user.id,
            product_id=product_id,
            delivery_date=delivery_date,
            delivery_location=request.form['location']
        )

        db.session.add(order)
        db.session.commit()

        flash(f'Order placed successfully! (Order #{order.id})', 'success')
        return redirect(url_for('my_orders'))

    return render_template('order.html', product=product)


# -------------------------------------------------
# ADMIN ROUTES
# -------------------------------------------------

@app.route('/admin')
@admin_required
def admin_dashboard():

    user_count = User.query.count()
    pending_users = User.query.filter_by(is_confirmed=False).count()
    product_count = Product.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()

    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

    return render_template(
        'admin/dashboard.html',
        user_count=user_count,
        pending_users=pending_users,
        product_count=product_count,
        pending_orders=pending_orders,
        recent_users=recent_users,
        recent_orders=recent_orders
    )


@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    pending_count = sum(1 for u in users if not u.is_confirmed)  # count pending users
    return render_template(
        'admin/users.html',
        users=users,
        pending_count=pending_count
    )


@app.route('/admin/confirm/<int:user_id>')
@admin_required
def confirm_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_confirmed = True
    db.session.commit()
    flash(f'User confirmed successfully!', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/upload', methods=['GET', 'POST'])
@admin_required
def admin_upload():

    categories = Category.query.all()

    if request.method == 'POST':

        product = Product(
            name=request.form['name'],
            price=float(request.form['price']),
            description=request.form['description'],
            category_id=int(request.form['category']),
            is_new='is_new' in request.form,
            is_hot='is_hot' in request.form
        )

        db.session.add(product)
        db.session.commit()

        files = request.files.getlist('photos')

        photo_filenames = []
        thumbnail_filename = None

        for i, file in enumerate(files[:4]):
            if file and file.filename:

                filename = secure_filename(f"{product.id}_{i}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                photo_filenames.append(filename)

                if i == 0:
                    thumb_filename = f"thumb_{filename}"
                    thumb_path = os.path.join(
                        app.config['UPLOAD_FOLDER'],
                        'thumbnails',
                        thumb_filename
                    )

                    try:
                        with Image.open(filepath) as img:
                            img.thumbnail(app.config['THUMBNAIL_SIZE'])
                            img.save(thumb_path, 'JPEG', quality=85)

                        thumbnail_filename = f"thumbnails/{thumb_filename}"

                    except Exception as e:
                        print("Thumbnail error:", e)

        product.photos = json.dumps(photo_filenames) if photo_filenames else None
        product.thumbnail = thumbnail_filename

        db.session.commit()

        flash(f'Product "{product.name}" uploaded successfully!', 'success')
        return redirect(url_for('admin_products'))

    return render_template('admin/upload.html', categories=categories)

# -------------------------------------------------
# ORDERS - ADMIN
# -------------------------------------------------

@app.route('/admin/orders')
@login_required
def admin_orders():
    # your existing code
    orders = Order.query.all()  # example
    pending_count = Order.query.filter_by(status='pending').count()
    confirmed_count = Order.query.filter_by(status='confirmed').count()

    return render_template(
        'admin/orders.html',
        orders=orders,
        pending_count=pending_count,
        confirmed_count=confirmed_count,
        datetime=datetime  # <-- pass it here
    )

@app.route('/admin/confirm-order/<int:order_id>')
@admin_required
def admin_confirm_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == 'pending':
        order.status = 'confirmed'
        db.session.commit()
        flash(f'Order #{order.id} confirmed successfully!', 'success')
    else:
        flash('Order already confirmed', 'info')
    return redirect(url_for('admin_orders'))

# -------------------------------------------------
# ORDERS - USER
# -------------------------------------------------

@app.route('/my-orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'my_orders.html',
        orders=orders,
        admin_phone='23280401927',
        datetime=datetime  # <-- make datetime available in template
        
    )
# -------------------------------------------------
# API ROUTE
# -------------------------------------------------

@app.route('/api/products')
@login_required
def api_products():

    if not current_user.is_confirmed and not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    products = Product.query.limit(20).all()

    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'price': float(p.price),
            'thumbnail': url_for(
                'static',
                filename=f"uploads/{p.thumbnail}"
            ) if p.thumbnail else None,
            'category': p.category.name if p.category else None
        }
        for p in products
    ])


# -------------------------------------------------

if __name__ == '__main__':
    app.run(debug=True)