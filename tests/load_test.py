"""Load testing script for support-bot."""
import asyncio
import aiohttp
import time
from typing import List
import statistics

# Configuration
BASE_URL = "http://localhost:8080"  # Change to your bot API
NUM_USERS = 100
MESSAGES_PER_USER = 10
CONCURRENT_USERS = 10


class LoadTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.response_times: List[float] = []
        self.errors = 0
        self.success = 0
    
    async def send_message(self, session: aiohttp.ClientSession, user_id: int, message: str):
        """Simulate sending a message."""
        start = time.time()
        try:
            async with session.post(
                f"{self.base_url}/api/message",
                json={"user_id": user_id, "text": message},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    self.success += 1
                else:
                    self.errors += 1
                
                elapsed = time.time() - start
                self.response_times.append(elapsed)
        except Exception as e:
            self.errors += 1
            print(f"Error: {e}")
    
    async def simulate_user(self, session: aiohttp.ClientSession, user_id: int):
        """Simulate a single user sending multiple messages."""
        for i in range(MESSAGES_PER_USER):
            await self.send_message(
                session,
                user_id,
                f"Test message {i} from user {user_id}"
            )
            await asyncio.sleep(0.1)  # Small delay between messages
    
    async def run_load_test(self):
        """Run the load test."""
        print(f"Starting load test:")
        print(f"  Users: {NUM_USERS}")
        print(f"  Messages per user: {MESSAGES_PER_USER}")
        print(f"  Concurrent users: {CONCURRENT_USERS}")
        print(f"  Total messages: {NUM_USERS * MESSAGES_PER_USER}")
        print()
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Run users in batches
            for batch_start in range(0, NUM_USERS, CONCURRENT_USERS):
                batch_end = min(batch_start + CONCURRENT_USERS, NUM_USERS)
                tasks = [
                    self.simulate_user(session, user_id)
                    for user_id in range(batch_start, batch_end)
                ]
                await asyncio.gather(*tasks)
                print(f"Completed batch {batch_start}-{batch_end}")
        
        elapsed = time.time() - start_time
        
        # Print results
        print("\n" + "="*50)
        print("LOAD TEST RESULTS")
        print("="*50)
        print(f"Total time: {elapsed:.2f}s")
        print(f"Total requests: {self.success + self.errors}")
        print(f"Successful: {self.success}")
        print(f"Errors: {self.errors}")
        print(f"Success rate: {(self.success / (self.success + self.errors) * 100):.2f}%")
        print()
        
        if self.response_times:
            print("Response times:")
            print(f"  Min: {min(self.response_times):.3f}s")
            print(f"  Max: {max(self.response_times):.3f}s")
            print(f"  Mean: {statistics.mean(self.response_times):.3f}s")
            print(f"  Median: {statistics.median(self.response_times):.3f}s")
            print(f"  P95: {statistics.quantiles(self.response_times, n=20)[18]:.3f}s")
            print(f"  P99: {statistics.quantiles(self.response_times, n=100)[98]:.3f}s")
        
        print()
        print(f"Throughput: {(self.success + self.errors) / elapsed:.2f} req/s")
        print("="*50)


async def test_health_endpoint():
    """Test health check endpoint."""
    print("Testing health endpoint...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{BASE_URL}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ Health check passed: {data}")
                    return True
                else:
                    print(f"✗ Health check failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"✗ Health check error: {e}")
            return False


async def main():
    """Main entry point."""
    # Test health first
    healthy = await test_health_endpoint()
    if not healthy:
        print("\nWarning: Health check failed. Continuing anyway...")
    
    print("\nStarting load test in 3 seconds...")
    await asyncio.sleep(3)
    
    tester = LoadTester(BASE_URL)
    await tester.run_load_test()


if __name__ == "__main__":
    asyncio.run(main())
