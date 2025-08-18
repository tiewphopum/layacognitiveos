# Symbols Summary

- Root: `/Users/sgndev003/development/GitHub/layacognitiveos`

## `scripts/__init__.py`

## `scripts/demo_bootstrap.py`

**Functions**

- `main`

## `scripts/demo_cam.py`

**Functions**

- `_to_mapping`
- `_extract_from_mapping`
- `_find_motion_ratio`
- `_find_src_ts`
- `amain`
- `main`

## `scripts/demo_motion.py`

**Functions**

- `main`

## `scripts/real_cam.py`

**Classes**

- `RtspCamera` (init: bus, url, cam_id='cam0', hz=None, topic='s1.img')
- `WebcamCamera` (init: bus, device=0, cam_id='cam0', hz=None, topic='s1.img')

## `src/layaos/__init__.py`

## `src/layaos/adapters/storage.py`

**Classes**

- `AsyncStorage` (init: out_dir='data', max_queue=1024, prefix='evt')
- `StorageConfig`
- `LocalEventStorage` (init: cfg, logger=None)

**Functions**

- `_to_jsonable`

## `src/layaos/adapters/ws_hub.py`

**Classes**

- `WSHubClientConfig`
- `WSHubClient`

## `src/layaos/core/buffer.py`

**Classes**

- `RingBuffer` (init: capacity=256)

## `src/layaos/core/bus.py`

**Classes**

- `EventBus` (init: name='orchestrai.bus', daemon=True, maxlen=256)

## `src/layaos/core/clock.py`

**Classes**

- `BeatClock`

## `src/layaos/core/contracts.py`

**Classes**

- `Event`
- `BBox`
- `CellStat`
- `BaseEvent`
- `FrameEvent`
- `DetectionEvent`
- `ReasonEvent`
- `ActionEvent`

## `src/layaos/core/dispatcher.py`

**Classes**

- `Dispatcher`

## `src/layaos/core/factory.py`

## `src/layaos/core/log.py`

**Classes**

- `JsonHandler`

**Functions**

- `_maybe_load_dotenv`
- `setup`
- `get`
- `set_level`

## `src/layaos/core/metrics.py`

**Classes**

- `_Base`
- `Counter` (init: name, labels)
- `Gauge` (init: name, labels)
- `Histogram` (init: name, labels, maxlen=2048)
- `_Registry`
- `_Exporter` (init: interval_sec=5.0, json_mode=False, logger=None)
- `Timer` (init: hist_name)

**Functions**

- `_labels_key`
- `_pct`
- `inc_counter`
- `set_gauge`
- `observe_hist`
- `inc`
- `gauge_set`
- `start_exporter`
- `stop_exporter`
- `snapshot`
- `snapshot_all`
- `force_emit`

## `src/layaos/core/ports.py`

**Classes**

- `CameraSource`
- `MotionDetector`
- `StorageSink`
- `HubClient`

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

- `State5_Imagination` (init: cfg, bus, batch_size=1)

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

- `MotionFullFrame` (init: cfg, cam_id='cam0')

**Functions**

- `_get`

## `src/layaos/wire_config.py`

**Functions**

- `_imp`
- `_mk_cfg`
- `build_from_yaml`

## `tests/conftest.py`

**Functions**

- `_bootstrap_logging_and_metrics`

## `tests/test_backpressure.py`

**Functions**

- `test_backpressure_resilience`

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

## `tests/test_fault_tolerance.py`

**Functions**

- `test_fault_tolerance_random_exceptions`

## `tests/test_graceful_shutdown.py`

**Functions**

- `test_graceful_shutdown`

## `tests/test_latency_metrics.py`

**Functions**

- `test_latency_metrics_smoke`

## `tests/test_metrics_dump.py`

**Functions**

- `main`
- `test_step1`

## `tests/test_metrics_exporter_smoke.py`

**Functions**

- `test_metrics_exporter_emits_logs`

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

## `tests/test_semantic_memory.py`

**Functions**

- `sem`
- `test_add_and_get`
- `test_learn_overwrite`
- `test_exists_and_remove`
- `test_list_and_search`

## `tests/test_storage_roundtrip.py`

**Functions**

- `test_storage_roundtrip`

## `tests/test_ws_roundtrip.py`

**Functions**

- `test_ws_roundtrip`

## `tools/merge_sources.py`

**Functions**

- `load_config`
- `guess_lang`
- `read_file_text`
- `render_md`
- `render_plain`
- `main`

## `tools/summarize_symbols.py`

**Functions**

- `should_skip`
- `get_init_args`
- `scan_file`
- `main`

