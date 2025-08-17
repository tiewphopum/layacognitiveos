# Symbols Summary

- Root: `/Users/sgndev003/development/GitHub/layaos`

## `scripts/demo_motion.py`

**Functions**

- `parse_args`
- `main`

## `src/layaos/__init__.py`

## `src/layaos/adapters/storage.py`

**Classes**

- `StorageConfig`
- `LocalEventStorage` (init: cfg=…)

**Functions**

- `_safe_for_name`

## `src/layaos/adapters/ws_hub.py`

**Classes**

- `WSHubClientConfig`
- `WSHubClient`

## `src/layaos/core/buffer.py`

**Classes**

- `RingBuffer` (init: capacity=256)

## `src/layaos/core/bus.py`

**Classes**

- `InProcEventBus` (init: name='orchestrai.bus', daemon=True, maxlen=256)

## `src/layaos/core/clock.py`

**Classes**

- `BeatClock`

## `src/layaos/core/contracts.py`

**Classes**

- `Event`
- `DataPackage`

## `src/layaos/core/dispatcher.py`

**Classes**

- `Dispatcher`

## `src/layaos/core/log.py`

**Functions**

- `setup`
- `get`
- `_to_level`

## `src/layaos/core/metrics.py`

**Functions**

- `_nlabels`
- `_key`
- `inc`
- `gauge_set`
- `observe_hist`
- `snapshot`
- `reset`
- `counter`
- `gauge`
- `hist`

## `src/layaos/pipeline/state1_sensor.py`

**Classes**

- `State1_Sensor`

## `src/layaos/pipeline/state2_preproc.py`

**Classes**

- `State2_PreProc`

## `src/layaos/pipeline/state3_perception.py`

**Classes**

- `State3_Perception`

## `src/layaos/pipeline/state4_context.py`

**Classes**

- `State4_Context`

## `src/layaos/pipeline/state5_imagination.py`

**Classes**

- `State5_Imagination`

## `src/layaos/pipeline/state6_action.py`

**Classes**

- `State6_Action`

## `src/layaos/pipeline/state_base.py`

**Classes**

- `StateConfig`
- `PipelineState` (init: cfg, bus)

## `src/layaos/pipeline/wire_minimal.py`

**Functions**

- `build_pipeline`
- `run_pipeline`

## `src/layaos/synth/mock_camera.py`

**Classes**

- `MockCamConfig`
- `MockCamera` (init: config=…, bus=None, topic_out=None)

## `src/layaos/tools/check_dupes.py`

## `src/layaos/vision/motion_baseline.py`

**Classes**

- `MotionBaselineConfig`
- `MotionBaseline` (init: cfg=…)

## `src/layaos/vision/motion_fullframe.py`

**Classes**

- `DetectionEvent`
- `MotionFullFrame` (init: cfg)

## `tests/conftest.py`

## `tests/test_bus_flow.py`

**Classes**

- `DummyEvent` (init: topic, payload)

**Functions**

- `test_bus_publish_topic_and_event_dual_api`
- `test_bus_concurrent_producers_single_consumer`
- `test_bus_queue_depth_and_empty_try_consume`

## `tests/test_camera_to_bus.py`

**Functions**

- `test_camera_to_bus`

## `tests/test_frame.py`

**Functions**

- `test_basic`

## `tests/test_metrics_dump.py`

**Functions**

- `main`
- `test_step1`

## `tests/test_motion_pipeline.py`

**Functions**

- `test_motion_detection_from_mock_camera`

## `tests/test_orchestra_min.py`

**Functions**

- `test_orchestra_min_runs_without_errors`

## `tests/test_perf_basics.py`

**Functions**

- `pct`
- `run`
- `main`
- `test_step1`

## `tests/test_pipeline_min.py`

**Functions**

- `main`
- `test_step1`

## `tests/test_pipeline_motion_demo.py`

**Classes**

- `DemoConfig`

**Functions**

- `main`
- `test_step1`

## `tests/test_pipeline_s13_detection.py`

**Functions**

- `test_pipeline_emits_s3_detection`

## `tests/test_storage.py`

**Functions**

- `test_step1`

## `tests/test_ws_roundtrip.py`

**Functions**

- `test_ws_roundtrip`

## `tools/summarize_symbols.py`

**Functions**

- `should_skip`
- `get_init_args`
- `scan_file`
- `main`

