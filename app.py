from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import text, Column, String  # Add Column and String imports
import datetime
from datetime import timedelta
from dish import Dish
from person import Person
import requests
import json


app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecret'
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg2://default:mk2aS9URHwOf@ep-falling-fire-a4ke12jz.us-east-1.aws.neon.tech:5432/verceldb?sslmode=require"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
def init():
    global dishes, people_objects, month_models, test_today
    dishes = []
    people_objects = []
    start_date = datetime.datetime(2024, 1, 1)
    end_date = datetime.datetime(2024, 2, 1)
    month_models = generate_month_models(start_date, end_date)
    test_today = datetime.datetime.now()

@app.route('/')
def index():
    global lunch_owner, dinner_owner, x1_owner, people_objects, dishes

    if 'user' not in session:
        return redirect(url_for('login'))

    # Generate dish objects for all months
    create_all_dish_objects()
    
    # Create people objects
    create_people_objects()

    user = session['user']
    person = None
    for people in people_objects:
        if people.name == user:
            person = people

    today = datetime.date.today()

    # Skip Saturday
    if today.strftime("%A") == 'Saturday':
        today += timedelta(days=1)

    # Check if today is within the date range
    if start_date.date() <= today <= end_date.date():
        today_lunch = None
        today_dinner = None
        today_x1 = None

        for dish in dishes:
            if dish.date_obj == today:
                if dish.type == "lunch":
                    today_lunch = dish
                elif dish.type == "dinner":
                    today_dinner = dish
                elif dish.type == "x1":
                    today_x1 = dish

        lunch_owner = today_lunch.owner if today_lunch and today_lunch.owner else 'Not Assigned'
        dinner_owner = today_dinner.owner if today_dinner and today_dinner.owner else 'Not Assigned'
        x1_owner = today_x1.owner if today_x1 and today_x1.owner else 'Not Assigned'

    # Calculate points for non-admin users
    if user != 'admin':
        calculate_points(person)
    else:
        for person in people_objects:
            calculate_points(person)
    
    return render_template('index.html', dishes=dishes, user=user, person=person, people_objects=people_objects, test_today=test_today)

@app.route('/client')
def client():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    create_september_objects()
    create_october_objects()
    create_november_objects()
    create_december_objects()
    dishes = september_objects + october_objects + november_objects + december_objects
    my_dishes = []
    create_people_objects()
    user = session['user']
    person = None
    for people in people_objects:
        if people.name == user:
            person = people

    for dish in dishes:
        if dish.owner == person.name:
            my_dishes.append(dish)

    return render_template('client.html', my_dishes=my_dishes, person=person)

@app.route('/admin')
def admin():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    create_september_objects()
    create_october_objects()
    create_november_objects()
    create_december_objects()
    dishes = september_objects + october_objects + november_objects + december_objects
    create_people_objects()

    for person in people_objects:
        calculate_points(person)

    return render_template('admin.html', people_objects=people_objects)

@app.route('/rules')
def rules():
    return render_template('rules.html')

@app.route('/change-owner', methods=['POST'])
def change_owner():
    data = request.get_json()
    month = data.get('month')
    id = data.get('id')
    owner = data.get('owner')

    if owner is None:
        owner_value = 'NULL'
    else:
        owner_value = f"'{owner}'"

    db.session.execute(
        text(f"UPDATE {month} SET owner = {owner_value} WHERE id = '{id}'")
    )
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Dish owner updated successfully'}), 200
    
@app.route('/send-messages', methods=['POST'])
def send_groupme_messages():
    lunch_userid = None
    for person in people_objects:
        if person.name == lunch_owner:
            lunch_userid = person.userID
    dinner_userid = None
    for person in people_objects:
        if person.name == dinner_owner:
            dinner_userid = person.userID
    x1_userid = None
    for person in people_objects:
        if person.name == x1_owner:
            x1_userid = person.userID
    
    url = "https://api.groupme.com/v3/bots/post"

    def send_message(message, owner, owner_userid, owner_loci_start, owner_loci_end):
        data = {
            "text": message,
            "bot_id": "c9ed078f3de7c89547308a050a",
        }
        if owner != 'Not Assigned':
            data["attachments"] = [
                {
                    "type": "mentions",
                    "user_ids": [owner_userid],
                    "loci": [[owner_loci_start, owner_loci_end]]
                }
            ]
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(data))
        return response

    # Send lunch message
    lunch_message = f"Lunch: @{lunch_owner}"
    send_message(lunch_message, lunch_owner, lunch_userid, 7, 7 + len(lunch_owner))

    # Send dinner message
    dinner_message = f"Dinner: @{dinner_owner}"
    send_message(dinner_message, dinner_owner, dinner_userid, 8, 8 + len(dinner_owner))

    # Send x1 message
    x1_message = f"x1: @{x1_owner}"
    send_message(x1_message, x1_owner, x1_userid, 4, 4 + len(x1_owner))

    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        if username == 'admin':
            session['user'] = username
            return redirect(url_for('admin'))
        else:
            person = PeopleModel.query.filter_by(name=username).first()
            if person:
                session['user'] = username
                return redirect(url_for('client'))
            else:
                return render_template('login.html', error="User not found")
    return render_template('login.html')

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/initdish', methods=['POST', 'GET'])
def initdish():
    for month_name, model in month_models.items():
        db.session.execute(text(f"DELETE FROM {month_name.lower()}"))
        db.session.commit()

    types = ['lunch', 'dinner', 'x1']
    type_index = 0
    i = 0
    delta = datetime.timedelta(days=1)
    current_date = start_date

    while current_date <= end_date:
        day_of_week = current_date.strftime("%A")
        month_name = current_date.strftime('%B').lower()

        if day_of_week != "Saturday":
            if day_of_week == "Sunday" and type_index == 0:
                type_index = 1
            db.session.execute(
                text(f"INSERT INTO {month_name} (year, day, id, owner, type) "
                    f"VALUES ({current_date.year}, {current_date.day}, {i}, null, '{types[type_index]}')")
            )
            db.session.commit()
            i += 1
            
            if types[type_index] == 'x1':
                current_date += delta
            
            type_index = (type_index + 1) % len(types)
        else:
            current_date += delta
    
    return jsonify({'success': True, 'message': 'Dishes initialized successfully'})

#Model Structures
def create_month_model(month_name):
    return type(
        f"{month_name.capitalize()}Model",
        (db.Model,),
        {
            "__tablename__": month_name.lower(),
            "year": Column(String),
            "day": Column(String),
            "id": Column(String, primary_key=True),
            "owner": Column(String),
            "type": Column(String),
        }
    )

def generate_month_models(start_date, end_date):
    current_date = start_date
    models = {}
    while current_date <= end_date:
        month_name = current_date.strftime('%B')
        if month_name not in models:
            models[month_name] = create_month_model(month_name)
        current_date += datetime.timedelta(days=1)
    return models

def create_dish_objects(month_name):
    model = month_models[month_name]
    dish_rows = model.query.all()
    dish_objects = []
    for row in dish_rows:
        dish_obj = Dish(
            year=int(row.year),
            month=datetime.datetime.strptime(month_name, '%B').month,
            day=int(row.day),
            type=row.type,
            owner=row.owner,
            id=row.id
        )
        dish_objects.append(dish_obj)
    dish_objects.sort(key=lambda dish: int(dish.id))
    return dish_objects

def create_all_dish_objects():
    global dishes
    dishes = []
    for month in month_models.keys():
        dishes += create_dish_objects(month)

@app.route("/people_objects")
def create_people_objects():
    global people_objects
    people_rows = PeopleModel.query.all()
    people_objects = []
    for row in people_rows:
        person_obj = Person(name=row.name, userID=row.userid, pickOrder=row.pickorder, totalPoints=row.totalpoints)
        people_objects.append(person_obj)

    people_objects.sort(key=lambda person: int(person.pickOrder))
    return {"people": [person.to_dict() for person in people_objects]}

def calculate_points(person):
    points = int(person.totalPoints)
    for dish in dishes:
        if person.name == dish.owner:
            if dish.weekday == 'Sunday' and dish.type == 'dinner':
                points -= 3
            elif (dish.type == 'lunch' or dish.type == 'dinner') and dish.weekday != 'Sunday':
                points -= 2
            elif dish.type == 'x1':
                points -= 1
    person.pointsNeeded = str(points)

init()
