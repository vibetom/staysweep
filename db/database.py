"""
Async SQLite database for the Hotel Hunter agent.
Stores hotels, reviews, images, and match results.
"""

import aiosqlite
import asyncio
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "hotel_hunter.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS hotels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                city        TEXT NOT NULL,
                address     TEXT,
                source      TEXT,
                source_url  TEXT UNIQUE,
                rating      REAL,
                fetched_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id    INTEGER REFERENCES hotels(id),
                source      TEXT,
                author      TEXT,
                rating      REAL,
                text        TEXT,
                review_url  TEXT,
                fetched_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id    INTEGER REFERENCES hotels(id),
                url         TEXT UNIQUE,
                source      TEXT,
                caption     TEXT,
                image_type  TEXT,   -- 'official' | 'guest'
                fetched_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS analysis_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id        INTEGER REFERENCES hotels(id),
                query           TEXT,
                text_score      REAL,
                vision_score    REAL,
                final_score     REAL,
                evidence_text   TEXT,   -- JSON list of matching review snippets
                evidence_images TEXT,   -- JSON list of matching image URLs
                summary         TEXT,
                analyzed_at     TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()


async def upsert_hotel(db, name, city, source, source_url, address=None, rating=None):
    await db.execute("""
        INSERT INTO hotels (name, city, address, source, source_url, rating)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_url) DO UPDATE SET
            rating=excluded.rating,
            fetched_at=datetime('now')
    """, (name, city, address, source, source_url, rating))
    await db.commit()
    cursor = await db.execute("SELECT id FROM hotels WHERE source_url=?", (source_url,))
    row = await cursor.fetchone()
    return row[0]


async def insert_review(db, hotel_id, source, text, author=None, rating=None, review_url=None):
    await db.execute("""
        INSERT OR IGNORE INTO reviews (hotel_id, source, author, rating, text, review_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (hotel_id, source, author, rating, text, review_url))
    await db.commit()


async def insert_image(db, hotel_id, url, source, caption=None, image_type="official"):
    await db.execute("""
        INSERT OR IGNORE INTO images (hotel_id, url, source, caption, image_type)
        VALUES (?, ?, ?, ?, ?)
    """, (hotel_id, url, source, caption, image_type))
    await db.commit()


async def get_hotels_for_city(db, city):
    cursor = await db.execute(
        "SELECT id, name, source_url FROM hotels WHERE LOWER(city)=LOWER(?)", (city,)
    )
    return await cursor.fetchall()


async def get_reviews_for_hotel(db, hotel_id, limit=50):
    cursor = await db.execute(
        "SELECT id, text, source, review_url FROM reviews WHERE hotel_id=? LIMIT ?",
        (hotel_id, limit)
    )
    return await cursor.fetchall()


async def get_images_for_hotel(db, hotel_id, limit=20):
    cursor = await db.execute(
        "SELECT id, url, source, image_type FROM images WHERE hotel_id=? LIMIT ?",
        (hotel_id, limit)
    )
    return await cursor.fetchall()


async def save_analysis(db, hotel_id, query, text_score, vision_score, final_score,
                        evidence_text, evidence_images, summary):
    await db.execute("""
        INSERT INTO analysis_results
            (hotel_id, query, text_score, vision_score, final_score,
             evidence_text, evidence_images, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        hotel_id, query, text_score, vision_score, final_score,
        json.dumps(evidence_text), json.dumps(evidence_images), summary
    ))
    await db.commit()


async def get_top_results(db, query, city, limit=5):
    cursor = await db.execute("""
        SELECT h.name, h.source_url, h.address, h.rating,
               a.final_score, a.text_score, a.vision_score,
               a.evidence_text, a.evidence_images, a.summary
        FROM analysis_results a
        JOIN hotels h ON h.id = a.hotel_id
        WHERE LOWER(h.city)=LOWER(?) AND a.query=?
        ORDER BY a.final_score DESC
        LIMIT ?
    """, (city, query, limit))
    return await cursor.fetchall()
