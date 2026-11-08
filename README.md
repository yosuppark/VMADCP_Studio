# VM-ADCP Post-Processing Studio

**Vessel Mounted ADCP (선박 탑재 음향 도플러 유속계) 전용 후처리 및 분석 데스크톱 소프트웨어**

본 프로그램은 선박 탑재 ADCP 데이터의 정밀 후처리를 위한 오픈소스 데스크톱 애플리케이션입니다.  
**Sebastian Menze**의 IMR 연구선 ADCP 처리 절차([Processing-ADCP-data-from-IMR-vessels](https://github.com/sebastianmenze/Processing-ADCP-data-from-IMR-vessels)) 및 [CODAS 원리 가이드](https://github.com/sebastianmenze/Processing-and-analysis-of-large-ADCP-datasets/blob/master/Processing%20and%20analysis%20of%20vessel%20mounted%20and%20lowered%20ADCP%20data.md)에 기반하여 설계되었습니다.

---

## 🌟 주요 기능 (Core Capabilities)

### 1. 모션 보정 (Motion & Attitude Correction)
* **센서 레버암 오프셋 보정 (Sensor Lever-Arm Offset, $L_x, L_y, L_z$)**:
  * 선박 기준 좌표계에서 GNSS 안테나 위치와 ADCP 트랜스듀서 위치 사이의 3차원 상대 거리($\mathbf{L}$)를 정밀 보정합니다.
  * 선박이 파도나 조타로 각속도 $\boldsymbol{\omega} = (p, q, r)$로 회전할 때 발생하는 유도 속도 오차($\mathbf{v}_{lever} = \boldsymbol{\omega} \times \mathbf{L}$)를 실시간 계산하여 ADCP 트랜스듀서 위치에서의 정확한 대지 선속을 복원합니다.
  * 트랜스듀서의 수평 위치(위도, 경도) 및 해수면 기준 장착 깊이(Transducer Draft)를 프로파일 수심에 자동 반영합니다.
* **방위 및 자세 오프셋 (Heading, Pitch, Roll Offsets)**:
  * 자이로컴퍼스(Gyrocompass) 또는 Dual-Antenna GNSS의 방위각 장착 바이어스($\Delta\psi$) 및 종/횡경사 오프셋을 보정합니다:
    $$\psi_{true} = (\psi_{measured} + \Delta\psi) \pmod{360^\circ}$$
* **3차원 자세 보정 (Pitch, Roll, Heading / Yaw)**:
  * 고주파(10 Hz) GNSS/INS(ANPP) 및 내장 AHRS 센서 데이터를 결합하여 Beam 좌표계 $\rightarrow$ Instrument XYZ 좌표계 $\rightarrow$ Earth ENU(East, North, Up) 좌표계로 정확하게 회전 변환합니다.
* **선박 이동 속도 제거 (Ship Velocity Removal)**:
  * GNSS 대지 속도($V_{gps\_east}, V_{gps\_north}$) 또는 Bottom-Track 속도를 측정 유속에서 차감하여 해수의 절대 참 유속(Ocean Velocity)을 산출합니다:
    $$u_{ocean} = u_{measured} + V_{ship\_east}$$
    $$v_{ocean} = v_{measured} + V_{ship\_north}$$
* **트랜스듀서 오정렬 각도($\phi$) 및 진폭 스케일($A$) 캘리브레이션**:
  * 선박 선수선(Fore-Aft line)과 트랜스듀서 물리적 장착 각도 사이의 미세 오차(Misalignment Angle $\phi$) 및 음속 오차/진폭 계수($A$)를 보정합니다:
    $$\begin{pmatrix} u_{cal} \\ v_{cal} \end{pmatrix} = A \begin{pmatrix} \cos\phi & -\sin\phi \\ \sin\phi & \cos\phi \end{pmatrix} \begin{pmatrix} u \\ v \end{pmatrix}$$
  * **원클릭 자동 보정 (Auto-Calibration)**: Bottom-Track 속도와 GPS 속도 간의 복소 최소자승법(Complex Least-Squares)을 통해 최적의 $\phi$와 $A$를 자동 추정합니다.

### 2. 바텀 추적 및 사이드롭 간섭 제거 (Bottom Tracking & Sidelobe Masking)
* **해저 수심 산출 (Bathymetry)**: 4개 빔의 사거리(Slant range)로부터 수직 수심($D = R \times \cos\theta$)을 정확하게 계산합니다.
* **사이드롭(Sidelobe) 반사층 마스킹**:
  * 음향 빔의 기하학적 특성상 해저면 수직 거리($D_{bottom}$)에 도달한 사이드롭 에코가 경사 빔($\theta=25^\circ$)의 주엽 신호와 간섭을 일으켜 해저면 부근 유속을 심각하게 왜곡합니다.
  * 물리 법칙에 따른 임계 컷오프 수심:
    $$D_{cut} = D_{bottom} \times \cos(\theta) - \Delta_{margin}$$
    (예: 25도 빔 각도 시 바닥 수심의 약 90% 이하 영역을 자동으로 마스킹(NaN 처리))

### 3. 후방산란 강도 처리 (Acoustic Backscatter & $S_v$ Processing)
* **체적 후방산란 강도(Volume Backscattering Strength, $S_v$ in dB)** 계산:
  * 에코 강도(RSSI / Counts / dB)를 물리 음향 단위인 $S_v$ (dB)로 변환:
    $$S_v = C + 20 \log_{10}(R) + 2 \alpha R + K_c (E - E_r)$$
* **기하학적 구면 확산 손실 보정**: $20 \log_{10}(R)$ Transmission Loss
* **해수 음향 흡수 감쇠 계수($\alpha$) 정밀 계산**:
  * Ainslie & McColm (1998) 고정밀 음향 흡수 모델을 적용하여 수온($T$), 염분($S$), 수심($D$), 주파수($f$)에 따른 흡수 손실($2\alpha R$)을 보정합니다.
* 해양 플랑크톤, 부유사(Sediment), 생물량(Biomass) 및 수온약층(Pycnocline) 분석에 활용 가능합니다.

### 4. GMT (Generic Mapping Tools) 형식 항적도 및 스크립트 출력
* **인터랙티브 항적도 (Track Chart & Vector Map)**:
  * GUI 캔버스에서 선박 궤적, 층별 유속 벡터(Stick Plot / Arrow), 시작/종료점, 유속 크기 컬러바 표시.
* **GMT 6 모던 모드 스크립트 원클릭 자동 생성**:
  * `plot_track_chart.bat` (Windows용 배치 파일)
  * `plot_track_chart.sh` (Linux / macOS용 쉘 스크립트)
* **GMT 전용 데이터 테이블 출력**:
  * `track_line.txt`: 선박 항적 (Longitude, Latitude)
  * `current_vectors.txt`: `gmt velo` 포맷 (Lon, Lat, U, V, $\sigma_u$, $\sigma_v$, Corr)
  * `bathymetry.xyz`: 해저 수심 (Lon, Lat, Depth)
  * `backscatter_layer.xyz`: 층평균 $S_v$ (Lon, Lat, $S_v$)

### 5. 데이터 입출력 및 포맷 지원 (Multi-Format I/O, adcpreader & pyadps Reference)
* **Teledyne RDI (TRDI) VM-ADCP 지원 (adcpreader & pyadps 연동)**:
  * Workhorse, Ocean Surveyor, Sentinel 등 TRDI 표준 바이너리 **PD0** (`.pd0`, `.enr`, `.sta`, `.lta`, `.rdi`) 완벽 파싱
  * [smerckel/adcpreader](https://github.com/smerckel/adcpreader) & [p-amol/pyadps](https://github.com/p-amol/pyadps) 기반 첨단 처리 체계:
    1. **다단계 좌표 변환 파이프라인**:
       `BEAM` $\rightarrow$ `INST (XYZ)` $\rightarrow$ `SHIP (SFU)` $\rightarrow$ `EARTH (ENU)` 및 역변환(`ENU` $\rightarrow$ `SFU` $\rightarrow$ `XYZ`)
    2. **3-Beam Solution 복원 알고리즘**:
       4개 빔 중 1개 빔이 거품, 음향 차폐 등으로 결측(NaN)되었을 때 Error Velocity = 0 가정을 통해 ($b_1 + b_2 = b_3 + b_4$) 3차원 유속을 유실 없이 복원
    3. **pyadps 표준 다단계 품질 관리(QC) 체계**:
       * **센서 건전성 점검 (`apply_sensor_health`)**: 선박의 심한 동요로 인한 트랜스듀서 틸트 각도($\text{Tilt} > 15^\circ$) 초과 핑 자동 마스킹
       * **신호 품질 점검 (`apply_signal_quality`)**: 에코 강도 임계치(Weak signal/Noise floor), 상관도, 에러 속도 필터링
       * **물리적 유속 한계 점검 (`apply_velocity_check`)**: 비정상적인 수평 유속 급변치($|U| > 3.5\text{ m/s}$) 및 비정상 연직 속도($|W| > 0.8\text{ m/s}$) 자동 제거
       * **자편각 보정 (Magnetic Declination, $\delta$)**: 내장 지자기 센서의 자북을 진북으로 회전 보정 ($\psi_{true} = \psi_{mag} + \delta$)
    4. **PD0 분할 파일 병합 도구 (pyadps-cat 기능 내장)**:
       `File -> Merge Multi-part PD0 Files...` 메뉴를 통해 메모리 한계로 분할 기록된 다수의 연속 PD0 파일을 단일 통합 파일로 원클릭 병합
    5. **16-bit 모듈로 체크섬 검증 및 스트리밍 제너레이터**:
       `verify_pd0_checksum()` 및 `RDIReader.iter_ensembles()`를 통한 대용량 손상/결측 핑의 안전한 저메모리 스트림 처리
  * Fixed Leader(주파수, 빔 수, 셀 수, 블랭킹, Upward/Downward, Convex/Concave), Variable Leader(시간, 수온, 염분, 자세), Velocity, Correlation, Echo Intensity, Bottom Track 블록 디코딩
  * VMDAS GPS Navigation 및 동반 NMEA 파일(`*.N1R`, `*.N2R`, `*.nav`) 자동 결합 지원
* **Nortek Signature VM 지원**:
  * `.SigVM` (AD2CP + ANPP 10Hz GNSS/INS 결합 컨테이너) 및 스탠드얼론 `.AD2CP` 바이너리 지원
* **스마트 자동 포맷 감지 (`load_adcp_dataset`)**:
  * 확장자 및 바이너리 매직 바이트(`0x7F 0x7F` for RDI, `PK\x03\x04` / `0xA5` for Nortek)를 분석하여 원클릭으로 기종 자동 판별
* **CSV 요약 시계열 & HDF5/NetCDF 내보내기**:
  * 가공된 전체 2D 유속/후방산란 격자 및 마스크 데이터 보존

---

## 🚀 빠른 시작 (Quick Start)

### 1. 파이썬 없이 바로 실행하기 (독립 실행형 배포판)
파이썬이나 관련 라이브러리가 전혀 설치되어 있지 않은 윈도우 PC에서도 즉시 실행할 수 있습니다:
* **실행 방법 1**: 루트 폴더의 [`Start_VMADCP_Studio.bat`](file:///c:/ADCP/Start_VMADCP_Studio.bat) 더블클릭
* **실행 방법 2**: [`dist\VMADCP_Studio\VMADCP_Studio.exe`](file:///c:/ADCP/dist/VMADCP_Studio/VMADCP_Studio.exe) 직접 더블클릭
* **다른 PC로 전달 시**: [`dist\VMADCP_Studio_Portable.zip`](file:///c:/ADCP/dist/VMADCP_Studio_Portable.zip) (약 80 MB) 파일만 복사하여 압축을 풀면 파이썬 설치 없이 모든 기능을 100% 동일하게 사용하실 수 있습니다.

### 2. 파이썬 소스 코드로 실행하기 (Python Environment)
* Python 3.9 이상
* 필수 라이브러리: `numpy`, `scipy`, `matplotlib`, `h5py`
* 실행 명령어:
  ```powershell
  python run_app.py
  ```

특정 데이터 파일을 바로 열면서 실행할 수도 있습니다:
```powershell
python run_app.py "01_VM-ADCP\Nortek\VM Acquisition\107628_20261029T042301UTC.SigVM"
```

---

## 🖥️ 화면 구성 및 사용 방법

1. **데이터 로드 (`File -> Open Nortek SigVM` 또는 상단 [📂 Open SigVM File] 버튼)**:
   * `.SigVM` 파일(또는 `.AD2CP`)을 선택하면 내부 AD2CP 수심 프로파일, Bottom Track, ANPP 고정밀 항법 데이터가 자동으로 파싱 및 시간 동기화됩니다.
2. **센서 오프셋 및 레버암 설정 (`Settings -> Sensor Offsets & Lever-Arm...` 또는 [⚙ Sensor Offsets...] 버튼, 단축키 `Ctrl+L`)**:
   * **GNSS to ADCP Lever-Arm**: 전후($L_x$), 좌우($L_y$), 수직($L_z$) 오프셋 및 트랜스듀서 흘수(Draft) 입력
   * **Heading & Attitude Offset**: 자이로/GNSS 방위각 오프셋($\Delta\psi$), 피치($\Delta\theta$), 롤($\Delta\phi$) 바이어스 입력
   * **선박 프리셋 관리**: `Save Preset...` / `Load Preset...`을 통해 조사선별 설정값 저장 및 재활용
   * `[ ✔ Apply & Reprocess ]`를 누르면 즉시 레버암 유도 속도 및 위치가 재계산됩니다.
3. **좌측 파라미터 조절 (Control Panel)**:
   * **오정렬 각도(φ)**: 선박 축과의 회전각 입력 (또는 `⚡ Auto-Calibrate (BT vs GPS)` 버튼 클릭 시 자동 계산)
   * **바텀 추적 & 사이드롭**: `Enable Sidelobe Cutoff` 체크 (기본값 ON, 안전 마진 0.5m)
   * **후방산란 처리**: 염분(PSU), 노이즈 플로어 설정
   * **품질 관리 (QC)**: 최소 상관도(% min correlation), 최대 오차 유속 임계치
   * 설정 후 `▶ Run Post-Processing` 버튼을 누르면 1초 만에 전 프로파일이 갱신됩니다.
3. **중앙 탭 뷰어 (Tabbed Visualizer)**:
   * **🌊 Current Velocities (2D)**: 절대 유속 크기, 동서 유속($U$), 남북 유속($V$), 연직 유속($W$), 상관도 2D 컬러맵 및 해저면/사이드롭 컷오프 라인 확인
   * **📡 Backscatter & Echo (Sv)**: 체적 후방산란 강도($S_v$, dB) 및 원시 Echo Intensity 컬러맵
   * **🗺 Cruise Track & Vectors (GMT)**: 선박 궤적 및 층별 유속 벡터 화살표 인터랙티브 지도
   * **📊 Depth Profile Inspector**: 시간 슬라이더를 이동하여 특정 앙상블의 1D 수심 프로파일 상세 확인
   * **📋 Survey QC & Statistics**: 유효 데이터 수용률, 선속, 수심 통계 요약 보고서
4. **GMT 출력 (`File -> Export GMT Track Chart & Script` 또는 [🗺 Export GMT Track Chart] 버튼)**:
   * 저장할 폴더를 선택하면 GMT 스크립트와 데이터 파일이 즉시 생성됩니다.
   * GMT가 설치된 PC에서 `plot_track_chart.bat`를 더블클릭하면 학술 논문/보고서 수준의 지도 그림(`VMADCP_Track_Chart.png`, `.pdf`)이 자동 렌더링됩니다.

---

## 📂 프로젝트 구조

```
c:\ADCP\
├── run_app.py                  # 데스크톱 프로그램 실행 엔트리포인트
├── vmadcp/                     # 핵심 알고리즘 패키지
│   ├── io/                     # 데이터 입출력 (SigVM, AD2CP, ANPP 파서)
│   ├── processing/             # 모션 보정, 바텀 트래킹, 후방산란, QC 필터
│   ├── export/                 # GMT 6 스크립트 및 CSV/NetCDF 내보내기
│   └── gui/                    # Tkinter + Matplotlib 데스크톱 UI
├── tests/                      # 자동화 검증 및 E2E 테스트 스위트
└── 01_VM-ADCP/                 # 실선 Nortek Signature500 측정 데이터
```

---

## 📚 참고 문헌
1. Menze, S. (Institute of Marine Research, Norway): *Processing ADCP data from IMR vessels*, [GitHub Repository](https://github.com/sebastianmenze/Processing-ADCP-data-from-IMR-vessels).
2. Menze, S.: *Processing and analysis of vessel mounted and lowered ADCP data*, [GitHub Markdown Guide](https://github.com/sebastianmenze/Processing-and-analysis-of-large-ADCP-datasets).
3. Firing, E., et al. (University of Hawaii): *Common Ocean Data Access System (CODAS) ADCP Processing Principles*.
4. Ainslie, M. A., & McColm, J. G. (1998): *A simplified formula for viscous and chemical absorption of sound in sea water*, J. Acoust. Soc. Am.
5. Deines, K. L. (1999): *Backscatter estimation using Broadband acoustic Doppler current profilers*, IEEE Proc. Sixth Working Conf. on Current Measurement.
