import time
import swarm

swarm.client = swarm.BlofinClient(swarm.load_blofin_credentials())
swarm.state.running = True
t0 = time.time()
elapsed = swarm.run_cycle()
print(f"CYCLE DONE in {elapsed}s (wall {time.time()-t0:.1f}s)")
