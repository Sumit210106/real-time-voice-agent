# Real-Time Voice AI Agent

> A production-grade proof-of-concept for real-time, low-latency, human-like voice conversations with AI.

![Status](https://img.shields.io/badge/status-active-brightgreen)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![Node](https://img.shields.io/badge/node-18+-green)

---

## Live Deployment

**Frontend (Vercel)**  
https://real-time-voice-agent-4h8i.vercel.app/

**Backend (Render)**  
https://real-time-voice-agent.onrender.com/

> ⚠️ **Note:** Due to cold starts and real-time audio constraints on free tiers, initial connection latency may be higher than local runs. Once warm, real-time performance stabilizes.

---

## What is this?

This project demonstrates a **complete real-time voice AI pipeline** — from microphone input to AI-generated speech output — with a strong focus on **low latency, natural conversational flow, and system observability**.

It serves as a foundation for:
- Voice assistants
- Conversational AI interfaces
- Real-time AI copilots
- Speech-driven applications

---

## Core Capabilities

- **Live audio streaming** via WebSockets  
- **Custom audio preprocessing** (noise handling + VAD integration)  
- **Accurate voice activity detection**  
- **Turn detection & utterance buffering**  
- **Real-time speech-to-text (STT)**  
- **Fast LLM-based response generation**  
- **Streaming text-to-speech (TTS)**  
- **Barge-in support** (interrupt the AI mid-response)  
- **Real-time observability dashboard**  
- **Multi-user concurrent sessions**  
- **Live context updates during active sessions**  
- **Web search integration for current information**

---

## System Architecture



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
│  │   Deepgram STT  ──>  Groq LLM  ──>  Deepgram/Cartesia    │   │
│  │   (nova-2)          (llama3-70b)    TTS (streaming)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## The “Streaming Bridge” Design

Instead of treating STT → LLM → TTS as strictly sequential steps, the system is designed as a **continuous streaming bridge**:

- STT emits partial transcripts
- LLM begins generating responses early
- TTS streams audio as tokens arrive

### Benefits
- Overlapping compute
- Lower perceived latency
- Immediate cancellation on barge-in
- No idle gaps between stages

---

## Custom Audio Processing

### Noise Handling
- Lightweight denoising applied before downstream processing
- Reduces ambient noise while preserving speech clarity
- Avoids heavy DSP that would increase latency

### Voice Activity Detection (VAD)
- Implemented using **Silero VAD** at a low level
- Tuned for conversational speech
- Filters background noise and non-speech segments

### Turn Detection
- Built on top of VAD + silence duration thresholds
- Distinguishes natural pauses from end-of-turn
- Balances responsiveness vs premature interruption

> Managed VAD or noise suppression services were intentionally avoided to retain control over latency and system behavior.

---

## Audio Configuration

| Property | Value |
|--------|------|
| Sample Rate | 16,000 Hz |
| Bit Depth | 16-bit PCM |
| Chunk Size | 4,096 samples (~256ms) |
| Transport | Binary WebSocket |

---

## AI Stack

| Component | Provider | Model | Rationale |
|--------|--------|------|-----------|
| STT | Deepgram | `nova-2-phonecall` | Low-latency streaming transcription |
| LLM | Groq | `llama3-70b-8192` | Extremely fast TTFT (~150ms) |
| TTS | Deepgram / Cartesia | Streaming PCM | Immediate playback |
| Search | Tavily | — | Real-time web context |

---

## Barge-In (Interruption Handling)

When the user interrupts the agent mid-response:

1. Frontend detects new speech
2. Backend cancels active LLM and TTS streams
3. Audio playback stops immediately
4. New utterance is processed normally

This creates a **natural, human-like conversational flow**.

---

## Real-Time Context Updates

The system supports **dynamic context injection during an active voice session**.

- Context can be updated via an API call while the WebSocket connection remains open
- Updated context is immediately applied to subsequent LLM prompts
- No session restart or pipeline reset is required

**Example use case:**  
An admin dashboard can change agent behavior mid-conversation (e.g., interviewer mode, task-specific instructions).

---

## Multi-User Session Management

- Each client establishes an independent WebSocket session
- Sessions maintain isolated:
  - Audio buffers
  - Conversation state
  - Cancellation tokens
- Shared provider clients are reused for efficiency
- No context or memory bleed between users

---

## Observability & Metrics

A real-time metrics panel displays:

- VAD end-of-speech detection time
- STT latency
- LLM time-to-first-token (TTFT)
- TTS initialization latency
- Total end-to-end latency
- Session state indicators (listening / thinking / speaking)

---

## Performance Benchmarks (Local)

| Metric | Observed |
|------|----------|
| STT Latency | 300–400 ms |
| LLM TTFT | 150–250 ms |
| TTS Startup | ~300 ms |
| **End-to-End** | **~1.3 seconds** |

> With edge deployment and WebRTC transport, sub-1s latency is achievable.

---

## Conversation Memory

- Conversation history is maintained **in-memory per session**
- Used to provide short-term conversational context
- Cleared when the session ends

Persistent cross-session memory is not yet implemented.

---

## Structured Logging

- Backend emits structured JSON logs
- Logs are tagged with session identifiers
- Enables tracing STT → LLM → TTS flows
- Supports latency analysis and debugging

---

## Scaling Considerations

### Current Limitations
- Single-node deployment
- In-memory session state
- CPU-bound under high concurrency
- Tested with 1–5 concurrent users

### Path to Production Scale

| Challenge | Approach |
|--------|--------|
| Session persistence | Redis-backed storage |
| Compute bottlenecks | Async worker pools |
| Audio latency | WebRTC transport |
| Traffic spikes | Backpressure & rate limiting |
| Global latency | Region-based STT/TTS |

---

## Design Tradeoffs

### Optimized For
- Low latency
- Natural conversational flow
- Clear system boundaries
- Observability-first debugging

### Intentionally Sacrificed
- Horizontal scaling (PoC scope)
- Crash recovery
- Advanced echo cancellation

---
## Multi-User Session Management

The system supports multiple concurrent users.

Each client establishes an independent WebSocket session with isolated:
- audio buffers
- VAD and turn-detection state
- conversation context
- cancellation tokens for barge-in

Sessions are fully isolated, with no context or memory bleed between users.
Shared STT, LLM, and TTS provider clients are reused for efficiency, avoiding
per-user heavy processes.


## Known Issues

1. Echo feedback without headphones
2. Barge-in buffer cleanup could be tighter
3. Memory growth during long sessions

---

## Future Improvements

- Adaptive VAD thresholds
- Redis-backed session memory
- WebRTC audio transport
- Token-level streaming TTS
- Provider fallback logic
- Production-grade echo cancellation

---

## Getting Started (Local)

### Prerequisites
- Node.js 18+
- Python 3.11+
- ffmpeg
- API keys:
  - Deepgram
  - Groq
  - Tavily (optional)

### Setup

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