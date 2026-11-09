import threading

# Serialises every use of the shared, app-scoped embedder (pipeline batches and search
# queries). A threading.Lock does not bind to an event loop, unlike asyncio.Semaphore.
EMBED_LOCK = threading.Lock()
