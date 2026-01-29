# Real-Time Voice AI Agent

> A production-grade proof-of-concept for real-time, low-latency voice conversations with AI.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Node](https://img.shields.io/badge/node-18+-green)

---

## What is this?

This project demonstrates a **complete voice AI pipeline** — from microphone input to AI-generated speech output — with a focus on minimizing latency at every step. Think of it as building the foundation for voice assistants, real-time translators, or conversational AI interfaces.

The system handles:
- **Live audio streaming** via WebSockets
- **Noise suppression** for cleaner input
- **Voice activity detection** to know when you're speaking
- **Speech-to-text** transcription in real-time
- **LLM-powered responses** that understand context
- **Text-to-speech** that streams back to your browser
- **Barge-in support** — interrupt the AI mid-sentence, just like a real conversation

---

**The core challenge:** Get the total round-trip latency (speech → AI response → audio playback) as low as possible while maintaining reliability.

---

## How It Works

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         BROWSER                                 │
│  ┌─────────────┐                           ┌─────────────────┐  │
│  │ Microphone  │ ────── PCM Audio ──────>  │  Audio Player   │  │
│  └─────────────┘                           └─────────────────┘  │
└────────────┬────────────────────────────────────────▲───────────┘
             │                                        │
             │ WebSocket                    WebSocket │
             ▼                                        │
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI SERVER                             │
│                                                                 │
│  ┌──────────────┐    ┌─────────────┐    ┌───────────────────┐   │
│  │ Noise Hero   │ ─> │ VAD Engine  │ ─> │ Utterance Buffer  │   │
│  │ (Denoise)    │    │ (Silero)    │    │                   │   │
│  └──────────────┘    └─────────────┘    └─────────┬─────────┘   │
│                                                   │             │
│                                                   ▼             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              STREAMING AI PIPELINE                       │   │
│  │                                                          │   │
│  │   Deepgram STT  ──>  Groq LLM  ──>  Deepgram/Cartesia   │   │
│  │   (nova-2)          (llama3-70b)    TTS (streaming)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### The "Streaming Bridge" Approach

Instead of treating STT → LLM → TTS as three separate steps that run sequentially, I designed the system as a **continuous streaming bridge**. Each component starts processing as soon as it receives partial input from the previous stage.

This approach enables:
- **Overlapping compute** — LLM starts generating while STT is still transcribing
- **Early cancellation** — If you start speaking (barge-in), pending operations are cancelled immediately
- **Minimal idle time** — No waiting for one stage to fully complete before starting the next

---

## Technical Details

### Audio Configuration

| Property | Value | Rationale |
|----------|-------|-----------|
| Sample Rate | 16,000 Hz | Standard for speech recognition |
| Bit Depth | 16-bit signed integer | Balance of quality and bandwidth |
| Chunk Size | 4,096 samples (~256ms) | Optimized for VAD responsiveness |
| Transport | Binary WebSocket | Low overhead, real-time capable |

### AI Stack

| Component | Provider | Model | Why This Choice |
|-----------|----------|-------|-----------------|
| **STT** | Deepgram | `nova-2-phonecall` | Best-in-class latency for conversational speech |
| **LLM** | Groq | `llama3-70b-8192` | Incredibly fast TTFT (~150ms), quality reasoning |
| **TTS** | Deepgram/Cartesia | Streaming PCM | No WAV headers, immediate playback |

### Barge-In (Interruption Handling)

One of the trickiest parts of voice AI is handling interruptions naturally. When the user starts speaking while the AI is responding:

1. Frontend detects `speech_start` event
2. Backend immediately cancels:
   - Any active LLM generation tasks
   - Ongoing TTS synthesis streams
3. An explicit `interrupt` signal is sent to the client
4. Audio playback stops cleanly
5. The new user utterance is processed normally

This creates the natural back-and-forth of human conversation.

---

## Performance

### Latency Benchmarks (Local Testing)

| Metric | Observed Range | Target |
|--------|----------------|--------|
| STT Processing | 300–400ms | — |
| LLM Time-to-First-Token | 150–250ms | — |
| TTS Initialization | ~300ms | — |
| **Total End-to-End** | **~1.3 seconds** | < 1.0s |

> **Note:** These numbers are from local development. With edge deployment and further optimization, sub-1-second latency is achievable.

### Observability

The frontend includes a real-time metrics panel showing:
- Turn timing and duration
- Signal activity visualization
- Per-component latency breakdown
- Session state indicators

---

## Getting Started

### Prerequisites

- **Node.js** 18 or higher
- **Python** 3.11 or higher
- **ffmpeg** installed on your system
- API keys for:
  - [Deepgram](https://deepgram.com/) (STT & TTS)
  - [Groq](https://groq.com/) (LLM)
  - [Tavily](https://tavily.com/) (for web search)

### Installation

**1. Clone the repository**

```bash
git clone <repo-url>
cd real-time-voice-agent
```

**2. Set up the backend**

```bash
cd backend
python -m venv venv
source venv/bin/activate  
pip install -r requirements.txt
```

**3. Set up the frontend**

```bash
cd frontend
npm install
```

**4. Configure environment variables**

Create a `.env` file in directory:

```env
DEEPGRAM_API_KEY=your_deepgram_key
GROQ_API_KEY=your_groq_key
TAVILY_API_KEY=optional_tavily_key
```

**5. Run the application**

In one terminal (backend):
```bash
cd backend
python run.py
```

In another terminal (frontend):
```bash
cd frontend
npm run dev
```

**6. Open your browser**

Navigate to [http://localhost:3000](http://localhost:3000) and allow microphone access.

---

## Scaling Considerations

### Current Limitations

This is a **single-node proof-of-concept**. Current constraints:

- Sessions stored in-memory (lost on restart)
- CPU-bound for concurrent users
- Tested with 1–5 simultaneous connections

### Path to Production Scale

For 10× to 100× scale, I'd recommend:

| Challenge | Solution |
|-----------|----------|
| Session persistence | Migrate to Redis |
| Processing bottlenecks | Separate STT/LLM/TTS into async worker pools |
| Traffic spikes | Add backpressure and rate-limiting |
| Geographic latency | Deploy STT/TTS at edge locations |
| Audio transport | Consider WebRTC for sub-200ms delivery |

---

## Design Decisions

### What I Optimized For

- **Low latency** — The primary constraint driving all decisions
- **Real-time interactivity** — Natural conversation flow
- **Observability** — Can't improve what you can't measure
- **Clear boundaries** — Each component has a well-defined responsibility

### What I Intentionally Sacrificed

- Horizontal scalability (designed for single-node PoC)
- Session recovery after crashes
- Advanced acoustic echo cancellation

---

## Known Issues

1. **Echo feedback** — Without headphones, the AI's audio output can trigger VAD and create feedback loops
2. **Barge-in buffer flush** — Audio buffer cleanup during interruption could be tighter
3. **Memory growth** — Long sessions accumulate conversation history in memory

---

## Future Improvements

If I continue developing this, next on the list:

- [ ] Adaptive VAD thresholds based on ambient noise
- [ ] WebRTC transport for lower audio latency
- [ ] Redis-backed session storage
- [ ] Token-level streaming TTS (start speaking even faster)
- [ ] Production-grade echo cancellation

---