# sound-detection

**Bioacoustics monitoring for native yard restoration**  
Multi-microphone wildlife sound detection (bats, birds, noisy insects) with MLOps.  
Part of the [weathervane](https://github.com/dcaulton/weathervane) ecosystem.

## Quick Start (Development)

```bash
git clone https://github.com/dcaulton/sound-detection.git
cd sound-detection
make install          # ← this installs Torch correctly for your GPU
make dev              # starts FastAPI at http://localhost:8000
