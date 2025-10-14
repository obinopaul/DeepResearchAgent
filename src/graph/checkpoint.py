# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

import psycopg
from langgraph.store.memory import InMemoryStore
from psycopg.rows import dict_row
from pymongo import MongoClient

from src.config.loader import get_bool_env, get_str_env


class ChatStreamManager:
    """
    Manages chat stream messages with persistent storage and in-memory caching.

    This class handles the storage and retrieval of chat messages using both
    an in-memory store for temporary data and MongoDB or PostgreSQL for persistent storage.
    It tracks message chunks and consolidates them when a conversation finishes.

    Attributes:
        store (InMemoryStore): In-memory storage for temporary message chunks
        mongo_client (MongoClient): MongoDB client connection
        mongo_db (Database): MongoDB database instance
        postgres_conn (psycopg.Connection): PostgreSQL connection
        logger (logging.Logger): Logger instance for this class
    """

    def __init__(
        self, checkpoint_saver: bool = False, db_uri: Optional[str] = None
    ) -> None:
        """
        Initialize the ChatStreamManager with database connections.

        Args:
            db_uri: Database connection URI. Supports MongoDB (mongodb://) and PostgreSQL (postgresql://)
                   If None, uses LANGGRAPH_CHECKPOINT_DB_URL env var or defaults to localhost
        """
        self.logger = logging.getLogger(__name__)
        self.store = InMemoryStore()
        self.checkpoint_saver = checkpoint_saver
        # Use provided URI or fall back to environment variable or default
        self.db_uri = db_uri

        # Initialize database connections
        self.mongo_client = None
        self.mongo_db = None
        self.postgres_conn = None

        if self.checkpoint_saver:
            if self.db_uri.startswith("mongodb://") or self.db_uri.startswith("mongodb+srv://"):
                self._init_mongodb()
            elif self.db_uri.startswith("postgresql://") or self.db_uri.startswith(
                "postgres://"
            ):
                self._init_postgresql()
            else:
                self.logger.warning(
                    f"Unsupported database URI scheme: {self.db_uri}. "
                    "Supported schemes: mongodb://, postgresql://, postgres://"
                )
        else:
            self.logger.warning("Checkpoint saver is disabled")

    def _init_mongodb(self) -> None:
        """Initialize MongoDB connection."""

        try:
            self.mongo_client = MongoClient(self.db_uri)
            self.mongo_db = self.mongo_client.checkpointing_db
            # Test connection
            self.mongo_client.admin.command("ping")
            self.logger.info("Successfully connected to MongoDB")
        except Exception as e:
            self.logger.error(f"Failed to connect to MongoDB: {e}")

    def _init_postgresql(self) -> None:
        """Initialize PostgreSQL connection and create table if needed."""

        try:
            self.postgres_conn = psycopg.connect(self.db_uri, row_factory=dict_row)
            self.logger.info("Successfully connected to PostgreSQL")
            self._create_chat_streams_table()
        except Exception as e:
            self.logger.error(f"Failed to connect to PostgreSQL: {e}")

    def _create_chat_streams_table(self) -> None:
        """Create the chat_streams table if it doesn't exist."""
        try:
            with self.postgres_conn.cursor() as cursor:
                create_table_sql = """
                CREATE TABLE IF NOT EXISTS chat_streams (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    thread_id VARCHAR(255) NOT NULL UNIQUE,
                    messages JSONB NOT NULL,
                    ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_chat_streams_thread_id ON chat_streams(thread_id);
                CREATE INDEX IF NOT EXISTS idx_chat_streams_ts ON chat_streams(ts);
                """
                cursor.execute(create_table_sql)
                self.postgres_conn.commit()
                self.logger.info("Chat streams table created/verified successfully")
        except Exception as e:
            self.logger.error(f"Failed to create chat_streams table: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()

    def process_stream_message(
        self, thread_id: str, message: str, finish_reason: str
    ) -> bool:
        """
        Process and store a chat stream message chunk.

        This method handles individual message chunks during streaming and consolidates
        them into a complete message when the stream finishes. Messages are stored
        temporarily in memory and permanently in MongoDB when complete.

        Args:
            thread_id: Unique identifier for the conversation thread
            message: The message content or chunk to store
            finish_reason: Reason for message completion ("stop", "interrupt", or partial)

        Returns:
            bool: True if message was processed successfully, False otherwise
        """
        if not thread_id or not isinstance(thread_id, str):
            self.logger.warning("Invalid thread_id provided")
            return False

        if not message:
            self.logger.warning("Empty message provided")
            return False

        try:
            # Create namespace for this thread's messages
            store_namespace: Tuple[str, str] = ("messages", thread_id)

            # Get or initialize message cursor for tracking chunks
            cursor = self.store.get(store_namespace, "cursor")
            current_index = 0

            if cursor is None:
                # Initialize cursor for new conversation
                self.store.put(store_namespace, "cursor", {"index": 0})
            else:
                # Increment index for next chunk
                current_index = int(cursor.value.get("index", 0)) + 1
                self.store.put(store_namespace, "cursor", {"index": current_index})

            # Store the current message chunk
            self.store.put(store_namespace, f"chunk_{current_index}", message)

            # Check if conversation is complete and should be persisted
            if finish_reason in ("stop", "interrupt"):
                return self._persist_complete_conversation(
                    thread_id, store_namespace, current_index
                )

            return True

        except Exception as e:
            self.logger.error(
                f"Error processing stream message for thread {thread_id}: {e}"
            )
            return False

    def _persist_complete_conversation(
        self, thread_id: str, store_namespace: Tuple[str, str], final_index: int
    ) -> bool:
        """
        Persist completed conversation to database (MongoDB or PostgreSQL).

        Retrieves all message chunks from memory store and saves the complete
        conversation to the configured database for permanent storage.

        Args:
            thread_id: Unique identifier for the conversation thread
            store_namespace: Namespace tuple for accessing stored messages
            final_index: The final chunk index for this conversation

        Returns:
            bool: True if persistence was successful, False otherwise
        """
        try:
            # Retrieve all message chunks from memory store
            # Get all messages up to the final index including cursor metadata
            memories = self.store.search(store_namespace, limit=final_index + 2)

            # Extract message content, filtering out cursor metadata
            messages: List[str] = []
            for item in memories:
                value = item.dict().get("value", "")
                # Skip cursor metadata, only include actual message chunks
                if value and not isinstance(value, dict):
                    messages.append(str(value))

            if not messages:
                self.logger.warning(f"No messages found for thread {thread_id}")
                return False

            if not self.checkpoint_saver:
                self.logger.warning("Checkpoint saver is disabled")
                return False

            # Choose persistence method based on available connection
            if self.mongo_db is not None:
                return self._persist_to_mongodb(thread_id, messages)
            elif self.postgres_conn is not None:
                return self._persist_to_postgresql(thread_id, messages)
            else:
                self.logger.warning("No database connection available")
                return False

        except Exception as e:
            self.logger.error(
                f"Error persisting conversation for thread {thread_id}: {e}"
            )
            return False

    def _persist_to_mongodb(self, thread_id: str, messages: List[str]) -> bool:
        """Persist conversation to MongoDB."""
        try:
            # Get MongoDB collection for chat streams
            collection = self.mongo_db.chat_streams

            # Check if conversation already exists in database
            existing_document = collection.find_one({"thread_id": thread_id})

            current_timestamp = datetime.now()

            if existing_document:
                # Update existing conversation with new messages
                update_result = collection.update_one(
                    {"thread_id": thread_id},
                    {"$set": {"messages": messages, "ts": current_timestamp}},
                )
                self.logger.info(
                    f"Updated conversation for thread {thread_id}: "
                    f"{update_result.modified_count} documents modified"
                )
                return update_result.modified_count > 0
            else:
                # Create new conversation document
                new_document = {
                    "thread_id": thread_id,
                    "messages": messages,
                    "ts": current_timestamp,
                    "id": uuid.uuid4().hex,
                }
                insert_result = collection.insert_one(new_document)
                self.logger.info(
                    f"Created new conversation: {insert_result.inserted_id}"
                )
                return insert_result.inserted_id is not None

        except Exception as e:
            self.logger.error(f"Error persisting to MongoDB: {e}")
            return False

    def _persist_to_postgresql(self, thread_id: str, messages: List[str]) -> bool:
        """Persist conversation to PostgreSQL."""
        try:
            with self.postgres_conn.cursor() as cursor:
                # Check if conversation already exists
                cursor.execute(
                    "SELECT id FROM chat_streams WHERE thread_id = %s", (thread_id,)
                )
                existing_record = cursor.fetchone()

                current_timestamp = datetime.now()
                messages_json = json.dumps(messages)

                if existing_record:
                    # Update existing conversation with new messages
                    cursor.execute(
                        """
                        UPDATE chat_streams 
                        SET messages = %s, ts = %s 
                        WHERE thread_id = %s
                        """,
                        (messages_json, current_timestamp, thread_id),
                    )
                    affected_rows = cursor.rowcount
                    self.postgres_conn.commit()

                    self.logger.info(
                        f"Updated conversation for thread {thread_id}: "
                        f"{affected_rows} rows modified"
                    )
                    return affected_rows > 0
                else:
                    # Create new conversation record
                    conversation_id = uuid.uuid4()
                    cursor.execute(
                        """
                        INSERT INTO chat_streams (id, thread_id, messages, ts) 
                        VALUES (%s, %s, %s, %s)
                        """,
                        (conversation_id, thread_id, messages_json, current_timestamp),
                    )
                    affected_rows = cursor.rowcount
                    self.postgres_conn.commit()

                    self.logger.info(
                        f"Created new conversation with ID: {conversation_id}"
                    )
                    return affected_rows > 0

        except Exception as e:
            self.logger.error(f"Error persisting to PostgreSQL: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()
            return False

    def close(self) -> None:
        """Close database connections."""
        try:
            if self.mongo_client is not None:
                self.mongo_client.close()
                self.logger.info("MongoDB connection closed")
        except Exception as e:
            self.logger.error(f"Error closing MongoDB connection: {e}")

        try:
            if self.postgres_conn is not None:
                self.postgres_conn.close()
                self.logger.info("PostgreSQL connection closed")
        except Exception as e:
            self.logger.error(f"Error closing PostgreSQL connection: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connections."""
        self.close()


# Global instance for backward compatibility
# TODO: Consider using dependency injection instead of global instance
_default_manager = ChatStreamManager(
    checkpoint_saver=get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False),
    db_uri=get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "mongodb://localhost:27017"),
)


def chat_stream_message(thread_id: str, message: str, finish_reason: str) -> bool:
    """
    Legacy function wrapper for backward compatibility.

    Args:
        thread_id: Unique identifier for the conversation thread
        message: The message content to store
        finish_reason: Reason for message completion

    Returns:
        bool: True if message was processed successfully
    """
    checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
    if checkpoint_saver:
        return _default_manager.process_stream_message(
            thread_id, message, finish_reason
        )
    else:
        return False
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
#     # src/graph/checkpoint.py

# import json
# import logging
# import uuid
# from datetime import datetime
# from typing import List, Optional, Tuple

# import psycopg
# from langgraph.store.memory import InMemoryStore
# # --- CHANGE: Import the async connection pool ---
# from psycopg_pool import AsyncConnectionPool
# from psycopg.rows import dict_row
# from pymongo import MongoClient

# from src/config/loader import get_bool_env, get_str_env

# # --- CHANGE: Create a global variable for the pool to manage it as a singleton ---
# _postgres_pool: Optional[AsyncConnectionPool] = None

# # --- CHANGE: Make the entire class handle async operations ---
# class ChatStreamManager:
#     """
#     Manages chat stream messages with persistent storage and in-memory caching.
    
#     This class handles the storage and retrieval of chat messages using both
#     an in-memory store for temporary data and MongoDB or PostgreSQL for persistent storage.
#     It tracks message chunks and consolidates them when a conversation finishes.

#     Attributes:
#         store (InMemoryStore): In-memory storage for temporary message chunks
#         mongo_client (MongoClient): MongoDB client connection
#         mongo_db (Database): MongoDB database instance
#         postgres_pool (AsyncConnectionPool): PostgreSQL connection pool
#         logger (logging.Logger): Logger instance for this class
#     """

#     def __init__(
#         self, checkpoint_saver: bool = False, db_uri: Optional[str] = None
#     ) -> None:
#         self.logger = logging.getLogger(__name__)
#         self.store = InMemoryStore()
#         self.checkpoint_saver = checkpoint_saver
#         self.db_uri = db_uri
#         self.mongo_client = None
#         self.mongo_db = None
#         # This will be initialized asynchronously
#         self.postgres_pool = None

#     # --- CHANGE: Add an async initialization method ---
#     async def ainitialize(self):
#         """Asynchronously initialize database connections."""
#         if self.checkpoint_saver:
#             if self.db_uri.startswith("mongodb://"):
#                 self._init_mongodb() # This remains synchronous
#             elif self.db_uri.startswith("postgresql://") or self.db_uri.startswith("postgres://"):
#                 await self._init_postgresql()
#             else:
#                 self.logger.warning(
#                     f"Unsupported database URI scheme: {self.db_uri}. "
#                     "Supported schemes: mongodb://, postgresql://, postgres://"
#                 )
#         else:
#             self.logger.warning("Checkpoint saver is disabled")

#     def _init_mongodb(self) -> None:
#         """Initialize MongoDB connection."""
#         try:
#             self.mongo_client = MongoClient(self.db_uri)
#             self.mongo_db = self.mongo_client.checkpointing_db
#             self.mongo_client.admin.command("ping")
#             self.logger.info("Successfully connected to MongoDB")
#         except Exception as e:
#             self.logger.error(f"Failed to connect to MongoDB: {e}")

#     # --- CHANGE: Make PostgreSQL initialization async and use the pool ---
#     async def _init_postgresql(self) -> None:
#         """Initialize PostgreSQL connection pool and create table if needed."""
#         global _postgres_pool
#         if _postgres_pool is not None:
#             self.postgres_pool = _postgres_pool
#             self.logger.info("Reusing existing PostgreSQL connection pool.")
#             return

#         try:
#             # Create a new connection pool
#             # You can tune min_size, max_size, idle_timeout, etc.
#             _postgres_pool = AsyncConnectionPool(
#                 conninfo=self.db_uri,
#                 min_size=1,   # Minimum number of connections to keep open
#                 max_size=10,  # Maximum number of connections in the pool
#                 # Close connections that are idle for more than 300 seconds (5 minutes)
#                 idle_timeout=300,
#                 # Reconnect if a connection is older than 1 hour to prevent stale connections
#                 max_lifetime=3600,
#                 row_factory=dict_row
#             )
#             self.postgres_pool = _postgres_pool
#             await self.postgres_pool.open() # Wait for the pool to be ready
#             self.logger.info("Successfully created and connected PostgreSQL connection pool.")
#             await self._create_chat_streams_table()
#         except Exception as e:
#             self.logger.error(f"Failed to connect to PostgreSQL: {e}")
#             _postgres_pool = None
#             self.postgres_pool = None


#     # --- CHANGE: Make table creation async ---
#     async def _create_chat_streams_table(self) -> None:
#         """Create the chat_streams table if it doesn't exist."""
#         if not self.postgres_pool:
#             return
#         try:
#             # Borrow a connection from the pool for this operation
#             async with self.postgres_pool.connection() as aconn:
#                 async with aconn.cursor() as acur:
#                     create_table_sql = """
#                     CREATE TABLE IF NOT EXISTS chat_streams (
#                         id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#                         thread_id VARCHAR(255) NOT NULL UNIQUE,
#                         messages JSONB NOT NULL,
#                         ts TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
#                     );
#                     CREATE INDEX IF NOT EXISTS idx_chat_streams_thread_id ON chat_streams(thread_id);
#                     CREATE INDEX IF NOT EXISTS idx_chat_streams_ts ON chat_streams(ts);
#                     """
#                     await acur.execute(create_table_sql)
#             self.logger.info("Chat streams table created/verified successfully")
#         except Exception as e:
#             self.logger.error(f"Failed to create chat_streams table: {e}")

#     # --- CHANGE: Make the main processing method async ---
#     async def process_stream_message(
#         self, thread_id: str, message: str, finish_reason: str
#     ) -> bool:
#         """
#         Process and store a chat stream message chunk asynchronously.
#         """
#         if not thread_id or not isinstance(thread_id, str):
#             self.logger.warning("Invalid thread_id provided")
#             return False
#         if not message:
#             self.logger.warning("Empty message provided")
#             return False

#         try:
#             store_namespace: Tuple[str, str] = ("messages", thread_id)
#             cursor = self.store.get(store_namespace, "cursor")
#             current_index = 0

#             if cursor is None:
#                 self.store.put(store_namespace, "cursor", {"index": 0})
#             else:
#                 current_index = int(cursor.value.get("index", 0)) + 1
#                 self.store.put(store_namespace, "cursor", {"index": current_index})

#             self.store.put(store_namespace, f"chunk_{current_index}", message)

#             if finish_reason in ("stop", "interrupt"):
#                 # --- CHANGE: Await the async persistence method ---
#                 return await self._persist_complete_conversation(
#                     thread_id, store_namespace, current_index
#                 )

#             return True
#         except Exception as e:
#             self.logger.error(
#                 f"Error processing stream message for thread {thread_id}: {e}"
#             )
#             return False

#     # --- CHANGE: Make persistence async ---
#     async def _persist_complete_conversation(
#         self, thread_id: str, store_namespace: Tuple[str, str], final_index: int
#     ) -> bool:
#         """
#         Persist completed conversation to database (MongoDB or PostgreSQL) asynchronously.
#         """
#         try:
#             memories = self.store.search(store_namespace, limit=final_index + 2)
#             messages: List[str] = [
#                 str(item.dict().get("value", ""))
#                 for item in memories
#                 if item.dict().get("value") and not isinstance(item.dict().get("value"), dict)
#             ]

#             if not messages:
#                 self.logger.warning(f"No messages found for thread {thread_id}")
#                 return False

#             if not self.checkpoint_saver:
#                 self.logger.warning("Checkpoint saver is disabled")
#                 return False

#             if self.mongo_db is not None:
#                 return self._persist_to_mongodb(thread_id, messages)
#             elif self.postgres_pool is not None:
#                 # --- CHANGE: Await the async postgres method ---
#                 return await self._persist_to_postgresql(thread_id, messages)
#             else:
#                 self.logger.warning("No database connection available")
#                 return False
#         except Exception as e:
#             self.logger.error(
#                 f"Error persisting conversation for thread {thread_id}: {e}"
#             )
#             return False

#     def _persist_to_mongodb(self, thread_id: str, messages: List[str]) -> bool:
#         # This method can remain synchronous as pymongo has its own connection pooling
#         # ... (no changes needed here) ...
#         pass # Placeholder for your existing mongo logic

#     # --- CHANGE: Make the entire postgres persistence method async ---
#     async def _persist_to_postgresql(self, thread_id: str, messages: List[str]) -> bool:
#         """Persist conversation to PostgreSQL using the connection pool."""
#         if not self.postgres_pool:
#             self.logger.error("PostgreSQL connection pool is not initialized.")
#             return False
            
#         try:
#             # --- CRITICAL CHANGE: Borrow a connection from the pool for this single transaction ---
#             async with self.postgres_pool.connection() as aconn:
#                 async with aconn.cursor() as acur:
#                     await acur.execute(
#                         "SELECT id FROM chat_streams WHERE thread_id = %s", (thread_id,)
#                     )
#                     existing_record = await acur.fetchone()
                    
#                     current_timestamp = datetime.now()
#                     messages_json = json.dumps(messages)

#                     if existing_record:
#                         await acur.execute(
#                             """
#                             UPDATE chat_streams 
#                             SET messages = %s, ts = %s 
#                             WHERE thread_id = %s
#                             """,
#                             (messages_json, current_timestamp, thread_id),
#                         )
#                         affected_rows = acur.rowcount
#                         self.logger.info(
#                             f"Updated conversation for thread {thread_id}: "
#                             f"{affected_rows} rows modified"
#                         )
#                         return affected_rows > 0
#                     else:
#                         conversation_id = uuid.uuid4()
#                         await acur.execute(
#                             """
#                             INSERT INTO chat_streams (id, thread_id, messages, ts) 
#                             VALUES (%s, %s, %s, %s)
#                             """,
#                             (conversation_id, thread_id, messages_json, current_timestamp),
#                         )
#                         affected_rows = acur.rowcount
#                         self.logger.info(
#                             f"Created new conversation with ID: {conversation_id}"
#                         )
#                         return affected_rows > 0
#         except psycopg.Error as e: # Catch specific psycopg errors
#             self.logger.error(f"Error persisting to PostgreSQL: {e}")
#             # The pool handles connection state, no need to rollback manually
#             return False
#         except Exception as e:
#             self.logger.error(f"An unexpected error occurred during PostgreSQL persistence: {e}")
#             return False

#     # --- CHANGE: Make close method async to properly close the pool ---
#     async def aclose(self) -> None:
#         """Close database connections and the pool."""
#         if self.mongo_client is not None:
#             self.mongo_client.close()
#             self.logger.info("MongoDB connection closed")

#         global _postgres_pool
#         if _postgres_pool is not None:
#             await _postgres_pool.close()
#             _postgres_pool = None
#             self.postgres_pool = None
#             self.logger.info("PostgreSQL connection pool closed")

# # Global instance initialization needs to be rethought for an async world.
# # It's better to initialize it at the application startup.
# # For now, this legacy function will need to be async as well.

# async def get_default_manager() -> ChatStreamManager:
#     """Async factory for the default manager."""
#     manager = ChatStreamManager(
#         checkpoint_saver=get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False),
#         db_uri=get_str_env("LANGGRAPH_CHECKPOINT_DB_URL", "postgresql://user:password@host:port/dbname"),
#     )
#     await manager.ainitialize()
#     return manager


# # --- CHANGE: This legacy function must now be async ---
# async def chat_stream_message(thread_id: str, message: str, finish_reason: str) -> bool:
#     """
#     Asynchronously process a chat stream message using the default manager.
#     """
#     checkpoint_saver = get_bool_env("LANGGRAPH_CHECKPOINT_SAVER", False)
#     if checkpoint_saver:
#         manager = await get_default_manager()
#         return await manager.process_stream_message(
#             thread_id, message, finish_reason
#         )
#     else:
#         return False
