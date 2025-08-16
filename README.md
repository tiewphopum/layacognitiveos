# 🌌 LayaCognitiveOS (LCO)

**"Where cognition follows the rhythm of life."**  
LayaCognitiveOS (LCO) is an experimental *Cognitive Operating System* designed to **orchestrate** and **operate in rhythm-based cycles**, enabling AI modules to collaborate naturally and efficiently.

---

## ✨ Features
- **6 Cognitive States** – From sensor input to AI-driven decision making.  
- **Rhythm Engine (LayaCore)** – Each state works on its own *tick-phase cycle*, inspired by brain rhythms.  
- **Pluggable Components** – Easily add/remove sensors, AI models, or decision modules.  
- **Buffer-based Data Flow** – Process available data without waiting for the slowest state.  
- **Multi-camera Ready** – Scale from 1 to N cameras without blocking.  
- **Metrics & Logging** – Built-in performance logging and metrics collection.  

---

## 🧠 Architecture

```
State1: SensorAndInput
  Sensor(Camera) → KeyHubComponent → QueueBufferOutputComponent → SenderComponent

State2: PreProcessing
  ReceiveDataPackage → Dispatcher(Map) → Pipeline → DataPackManager → QueueBuffer → SendDataPackage

State3: Perception
  ReceiveDataPackage → ObjectDetection/Tracking → ObjectMemory → QueueBuffer → SendDataPackage

State4: ContextAndReasoning
  SceneUnderstanding → EventCorrelation → MemoryManager (Shared) → QueueBuffer → SendDataPackage

State5: ImaginationReasoning
  AIPromptBuilder → AIImaginationReasonDispatcher → GPTPipeline → ResultMerger → QueueBuffer → SendDataPackage

State6: DecisionAndAction
  AIPromptBuilder → AIDecisionAction → ActionScheduler → QueueBuffer → SendDataPackage
```

---

## 🚀 Quick Start

```bash
git clone https://github.com/YOURNAME/layacognitiveos.git
cd layacognitiveos
pip install -r requirements.txt

# Run demo
python -m tests.test_rhythm
```

---

## 🫀 Why Rhythm?

Instead of forcing all states to wait for each other, we let them follow **their own heartbeat**:  
- Each state has its **own rhythm** (tick/phase cycle)  
- They **sync** via shared buffers  
- If there's nothing in your buffer, you **rest** until the next beat  

This makes the system **smooth, scalable, and adaptive** — just like the natural rhythm of the brain 🧠

---

## 📦 Project Structure

```
src/
  core/       # Rhythm engine (LayaCore), state machine, base components
  vision/     # Camera, motion detection, object tracking
  synth/      # Simulation & synthetic data generators
  ws/         # WebSocket hub for real-time broadcast
tests/
  test_rhythm.py
  test_fullframe_motion.py
  ...
```

---

## 🪪 License
This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)** License.

- ✅ You are free to use, modify, and share this project for **personal, educational, or research purposes**.  
- ❌ Commercial use of this project (in whole or in part) is **not allowed**.  
- ℹ️ Any derivative works must also be distributed under the same license, with proper attribution.  

See the full license text here: [Creative Commons BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

---

## 👥 Authors
- **Pisit Tiewphopum** – System Architect & Lead Developer  
---

> 💡 *This is an experimental project — contributions, ideas, and remixes are welcome!*

