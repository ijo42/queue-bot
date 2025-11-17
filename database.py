import sqlite3
import logging
import os
from typing import List, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.getenv("DB_PATH", "queue_bot.db")
        self.db_path = db_path
        
        # Создаем директорию для БД если нужно
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def init_db(self):
        """Инициализация базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица очередей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    topic_id INTEGER DEFAULT 0,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(chat_id, topic_id, name)
                )
            """)
            
            # Таблица участников очереди
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queue_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    queue_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    position INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (queue_id) REFERENCES queues(id) ON DELETE CASCADE,
                    UNIQUE(queue_id, user_id)
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_queues_chat 
                ON queues(chat_id, topic_id, is_active)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_members_queue 
                ON queue_members(queue_id, position)
            """)
            
            logger.info("Database initialized successfully")

    def create_queue(self, chat_id: int, topic_id: int, name: str) -> Optional[int]:
        """Создать новую очередь"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO queues (chat_id, topic_id, name) VALUES (?, ?, ?)",
                    (chat_id, topic_id, name)
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.warning(f"Queue '{name}' already exists in chat {chat_id}, topic {topic_id}")
            return None

    def get_active_queue(self, chat_id: int, topic_id: int = 0) -> Optional[dict]:
        """Получить активную очередь для чата и топика"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM queues WHERE chat_id = ? AND topic_id = ? AND is_active = 1 LIMIT 1",
                (chat_id, topic_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def join_queue(self, queue_id: int, user_id: int, username: str, full_name: str) -> Optional[int]:
        """Добавить пользователя в очередь"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Получаем последнюю позицию
                cursor.execute(
                    "SELECT MAX(position) as max_pos FROM queue_members WHERE queue_id = ?",
                    (queue_id,)
                )
                result = cursor.fetchone()
                next_position = (result['max_pos'] or 0) + 1
                
                # Добавляем участника
                cursor.execute(
                    """INSERT INTO queue_members (queue_id, user_id, username, full_name, position) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (queue_id, user_id, username, full_name, next_position)
                )
                return next_position
        except sqlite3.IntegrityError:
            logger.warning(f"User {user_id} already in queue {queue_id}")
            return None

    def leave_queue(self, queue_id: int, user_id: int) -> bool:
        """Удалить пользователя из очереди"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем позицию удаляемого пользователя
            cursor.execute(
                "SELECT position FROM queue_members WHERE queue_id = ? AND user_id = ?",
                (queue_id, user_id)
            )
            result = cursor.fetchone()
            
            if not result:
                return False
            
            position = result['position']
            
            # Удаляем пользователя
            cursor.execute(
                "DELETE FROM queue_members WHERE queue_id = ? AND user_id = ?",
                (queue_id, user_id)
            )
            
            # Обновляем позиции остальных участников
            cursor.execute(
                "UPDATE queue_members SET position = position - 1 WHERE queue_id = ? AND position > ?",
                (queue_id, position)
            )
            
            return True

    def get_queue_members(self, queue_id: int) -> List[dict]:
        """Получить список участников очереди"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT user_id, username, full_name, position, joined_at 
                   FROM queue_members 
                   WHERE queue_id = ? 
                   ORDER BY position""",
                (queue_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def next_in_queue(self, queue_id: int) -> Optional[dict]:
        """Убрать первого в очереди и вернуть его данные"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получаем первого в очереди
            cursor.execute(
                """SELECT user_id, username, full_name, position 
                   FROM queue_members 
                   WHERE queue_id = ? 
                   ORDER BY position 
                   LIMIT 1""",
                (queue_id,)
            )
            result = cursor.fetchone()
            
            if not result:
                return None
            
            first_user = dict(result)
            
            # Удаляем первого пользователя
            cursor.execute(
                "DELETE FROM queue_members WHERE queue_id = ? AND position = 1",
                (queue_id,)
            )
            
            # Сдвигаем всех остальных
            cursor.execute(
                "UPDATE queue_members SET position = position - 1 WHERE queue_id = ?",
                (queue_id,)
            )
            
            return first_user

    def clear_queue(self, queue_id: int) -> int:
        """Очистить всех участников из очереди"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM queue_members WHERE queue_id = ?", (queue_id,))
            return cursor.rowcount

    def delete_queue(self, queue_id: int) -> bool:
        """Удалить очередь"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM queues WHERE id = ?", (queue_id,))
            return cursor.rowcount > 0

    def get_user_position(self, queue_id: int, user_id: int) -> Optional[int]:
        """Получить позицию пользователя в очереди"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT position FROM queue_members WHERE queue_id = ? AND user_id = ?",
                (queue_id, user_id)
            )
            result = cursor.fetchone()
            return result['position'] if result else None
