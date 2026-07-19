import asyncio

# Global semaphore to limit concurrent heavy analysis/summary jobs
analysis_semaphore = asyncio.Semaphore(1)  # 1 means single-threaded
