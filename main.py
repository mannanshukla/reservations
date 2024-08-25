from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import os
import json
import ollama

app = FastAPI()

# CORS Middleware Configuration
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:3000",  # Add your frontend URL here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Reservation(BaseModel):
    name: str
    phone_number: str
    time_slot: str
    party_size: int

class Transcript(BaseModel):
    transcript: str

# Establish a connection to the SQLite database
conn = sqlite3.connect("reservations.db")
c = conn.cursor()

# Create the reservations table if it doesn't exist
c.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone_number TEXT,
        time_slot TEXT,
        party_size INTEGER
    )
""")
conn.commit()

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    # Fetch the available time slots from the database
    with sqlite3.connect("reservations.db") as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT time_slot FROM reservations")
        booked_time_slots = [row[0] for row in c.fetchall()]

    # Load the HTML file
    with open("index.html", "r") as file:
        content = file.read()

    # Replace the placeholder with the booked time slots
    content = content.replace("{booked_time_slots}", ",".join(booked_time_slots) or "bg-gray-400")

    return HTMLResponse(content=content)

@app.post("/reservations")
def create_reservation(reservation: Reservation):
    # Convert the time slot string to a datetime object
    try:
        time_slot = datetime.strptime(reservation.time_slot, "%H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time slot format")

    # Check if the phone number already has a reservation
    with sqlite3.connect("reservations.db") as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM reservations WHERE phone_number = ?", (reservation.phone_number,))
        existing_reservation = c.fetchone()

    if existing_reservation:
        # Update the existing reservation
        with sqlite3.connect("reservations.db") as conn:
            c = conn.cursor()
            c.execute("UPDATE reservations SET name = ?, time_slot = ?, party_size = ? WHERE phone_number = ?", (
                reservation.name, reservation.time_slot, reservation.party_size, reservation.phone_number
            ))
            conn.commit()
        return {"message": "Reservation updated successfully"}
    else:
        # Check if the requested time slot is available
        with sqlite3.connect("reservations.db") as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM reservations WHERE time_slot = ?", (reservation.time_slot,))
            if c.fetchone():
                raise HTTPException(status_code=400, detail="Time slot is already booked")

            # Create a new reservation
            c.execute("INSERT INTO reservations (name, phone_number, time_slot, party_size) VALUES (?, ?, ?, ?)", (
                reservation.name, reservation.phone_number, reservation.time_slot, reservation.party_size
            ))
            conn.commit()
        return {"message": "Reservation created successfully"}

@app.get("/reservations/check-in")
def check_in(phone_number: str):
    # Check if the phone number has a reservation within the 5-minute window
    current_time = datetime.now()
    min_time = current_time - timedelta(minutes=5)
    max_time = current_time + timedelta(minutes=5)

    with sqlite3.connect("reservations.db") as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM reservations WHERE phone_number = ? AND time_slot BETWEEN ? AND ?", (
            phone_number, min_time.strftime("%H:%M"), max_time.strftime("%H:%M")
        ))
        reservation = c.fetchone()

    if reservation:
        return {"message": "Take a seat"}
    else:
        return {"message": "No reservation found"}

@app.get("/available-time-slots")
def get_available_time_slots():
    with sqlite3.connect("reservations.db") as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT time_slot FROM reservations")
        booked_time_slots = [row[0] for row in c.fetchall()]

    # Generate all possible time slots
    all_time_slots = []
    for hour in range(13, 20):  # From 1 PM to 7 PM
        for minute in [0, 30]:
            time_slot = f"{hour:02d}:{minute:02d}"
            all_time_slots.append(time_slot)

    # Calculate available time slots
    available_time_slots = [slot for slot in all_time_slots if slot not in booked_time_slots]

    return JSONResponse(content={"available_time_slots": available_time_slots})

@app.post("/analyze")
def analyze_transcript(transcript: Transcript):
    
    try:
        response = ollama.chat(model='analyze', messages=[
            {
                'role': 'user',
                'content': transcript.transcript
            }
        ])
        
        # Ensure the response is in JSON format
        try:
            json_response = json.loads(response['message']['content'])
        except json.JSONDecodeError:
            # If the response is not valid JSON, wrap it in a JSON object
            json_response = {"response": response['message']['content']}
        
        return JSONResponse(content=json_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error communicating with Ollama: {str(e)}")
