from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import os
from functools import wraps


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config["MONGO_URI"] = "mongodb+srv://laukik1:okokok@cluster0.y21lotg.mongodb.net/Doctor_Appointment"


mongo = PyMongo(app)

# Collections
users = mongo.db.users
appointments = mongo.db.appointments
print("MongoDB URI:", app.config["MONGO_URI"])
print("MongoDB Connection:", mongo.db)

# Constants
DOCTOR_NAME = "Dr. Prabhaker Patil"
DOCTOR_SPECIALTY = "General Physician"
APPOINTMENT_SLOTS = ["09:00 AM", "10:00 AM", "11:00 AM", "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM"]

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Home page
@app.route('/')
def home():
    return render_template('index.html', doctor_name=DOCTOR_NAME, doctor_specialty=DOCTOR_SPECIALTY)

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        
        # Check if user already exists
        existing_user = users.find_one({'email': email})
        if existing_user:
            flash('Email already registered', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        hashed_password = generate_password_hash(password)
        new_user = {
            'name': name,
            'email': email,
            'password': hashed_password,
            'phone': phone,
            'role': 'patient',
            'created_at': datetime.now()
        }
        
        user_id = users.insert_one(new_user).inserted_id
        
        # Login the user
        session['user_id'] = str(user_id)
        session['name'] = name
        session['role'] = 'patient'
        
        flash('Registration successful!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('register.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = users.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['name'] = user['name']
            session['role'] = user['role']
            
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))

# Dashboard route
@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'patient':
        # Get user's appointments
        user_appointments = list(appointments.find({'patient_id': session['user_id']}).sort('date', -1))
        return render_template('dashboard.html', appointments=user_appointments)
    else:
        # Get all appointments for admin/doctor
        all_appointments = list(appointments.find().sort('date', -1))
        return render_template('admin_dashboard.html', appointments=all_appointments)

# Book appointment route
@app.route('/book_appointment', methods=['GET', 'POST'])
@login_required
def book_appointment():
    if request.method == 'POST':
        date_str = request.form.get('date')
        time_slot = request.form.get('time_slot')
        reason = request.form.get('reason')
        
        # Convert date string to datetime object
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Check if the appointment slot is available
        existing_appointment = appointments.find_one({
            'date': appointment_date,
            'time_slot': time_slot
        })
        
        if existing_appointment:
            flash('This appointment slot is already booked', 'danger')
            return redirect(url_for('book_appointment'))
        
        # Create new appointment
        new_appointment = {
            'patient_id': session['user_id'],
            'patient_name': session['name'],
            'date': appointment_date,
            'time_slot': time_slot,
            'reason': reason,
            'doctor_name': DOCTOR_NAME,
            'status': 'scheduled',
            'created_at': datetime.now()
        }
        
        appointments.insert_one(new_appointment)
        flash('Appointment scheduled successfully', 'success')
        return redirect(url_for('dashboard'))
    
    # Calculate available dates (next 30 days)
    today = datetime.now().date()
    available_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 31)]
    
    # Get already booked slots
    booked_slots = {}
    for date in available_dates:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        booked_appointments = list(appointments.find({'date': date_obj}))
        booked_slots[date] = [app['time_slot'] for app in booked_appointments]
    
    return render_template('book_appointment.html', 
                          available_dates=available_dates, 
                          time_slots=APPOINTMENT_SLOTS,
                          booked_slots=booked_slots)

# View appointment details
@app.route('/appointment/<appointment_id>')
@login_required
def view_appointment(appointment_id):
    appointment = appointments.find_one({'_id': ObjectId(appointment_id)})
    
    if not appointment:
        flash('Appointment not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if the user is authorized to view this appointment
    if session['role'] == 'patient' and appointment['patient_id'] != session['user_id']:
        flash('You are not authorized to view this appointment', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('appointment_details.html', appointment=appointment)

# Cancel appointment
@app.route('/cancel_appointment/<appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    appointment = appointments.find_one({'_id': ObjectId(appointment_id)})
    
    if not appointment:
        flash('Appointment not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if the user is authorized to cancel this appointment
    if session['role'] == 'patient' and appointment['patient_id'] != session['user_id']:
        flash('You are not authorized to cancel this appointment', 'danger')
        return redirect(url_for('dashboard'))
    
    # Update appointment status
    appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {'status': 'cancelled', 'updated_at': datetime.now()}}
    )
    
    flash('Appointment cancelled successfully', 'success')
    return redirect(url_for('dashboard'))
# Update appointment route
@app.route('/update_appointment/<appointment_id>', methods=['GET', 'POST'])
@login_required
def update_appointment(appointment_id):
    # Get the appointment
    appointment = appointments.find_one({'_id': ObjectId(appointment_id)})
    
    if not appointment:
        flash('Appointment not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if the user is authorized to update this appointment
    if session['role'] == 'patient' and appointment['patient_id'] != session['user_id']:
        flash('You are not authorized to update this appointment', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if appointment is already cancelled or completed
    if appointment['status'] != 'scheduled':
        flash('Only scheduled appointments can be updated', 'warning')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        date_str = request.form.get('date')
        time_slot = request.form.get('time_slot')
        reason = request.form.get('reason')
        
        # Convert date string to datetime object
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Check if the appointment slot is available (excluding this appointment)
        existing_appointment = appointments.find_one({
            '_id': {'$ne': ObjectId(appointment_id)},
            'date': appointment_date,
            'time_slot': time_slot
        })
        
        if existing_appointment:
            flash('This appointment slot is already booked', 'danger')
            return redirect(url_for('update_appointment', appointment_id=appointment_id))
        
        # Update appointment
        appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {
                'date': appointment_date,
                'time_slot': time_slot,
                'reason': reason,
                'updated_at': datetime.now()
            }}
        )
        
        flash('Appointment updated successfully', 'success')
        return redirect(url_for('dashboard'))
    
    # Calculate available dates (next 30 days)
    today = datetime.now().date()
    available_dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 31)]
    
    # Get already booked slots
    booked_slots = {}
    for date in available_dates:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        # Exclude the current appointment from booked slots
        booked_appointments = list(appointments.find({
            '_id': {'$ne': ObjectId(appointment_id)},
            'date': date_obj
        }))
        booked_slots[date] = [app['time_slot'] for app in booked_appointments]
    
    return render_template('update_appointment.html', 
                          appointment=appointment,
                          available_dates=available_dates, 
                          time_slots=APPOINTMENT_SLOTS,
                          booked_slots=booked_slots)
# Admin routes (if you want to add admin functionality)
@app.route('/admin/appointments')
@login_required
def admin_appointments():
    if session['role'] != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    all_appointments = list(appointments.find().sort('date', -1))
    return render_template('admin_appointments.html', appointments=all_appointments)

# Update appointment status (for doctor/admin)
@app.route('/update_appointment_status/<appointment_id>', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    if session['role'] != 'admin':
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))
    
    status = request.form.get('status')
    notes = request.form.get('notes', '')
    
    appointments.update_one(
        {'_id': ObjectId(appointment_id)},
        {'$set': {
            'status': status,
            'notes': notes,
            'updated_at': datetime.now(),
            'updated_by': session['user_id']
        }}
    )
    
    flash('Appointment status updated', 'success')
    return redirect(url_for('admin_appointments'))

if __name__ == '__main__':
    # Create admin user if it doesn't exist
    admin = users.find_one({'role': 'admin'})
    if not admin:
        admin_user = {
            'name': DOCTOR_NAME,
            'email': 'doctor@example.com',
            'password': generate_password_hash('admin123'),
            'role': 'admin',
            'created_at': datetime.now()
        }
        users.insert_one(admin_user)
        print(f"Admin user created: {DOCTOR_NAME}")
    
    app.run(debug=True)