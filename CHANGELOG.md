# Changelog

## [0.1.19](https://github.com/Fuse-Technical-Group/pydecklink/compare/v0.1.18...v0.1.19) (2026-04-04)


### Added

* add cache to uv action to speed up ([57732b7](https://github.com/Fuse-Technical-Group/pydecklink/commit/57732b79189f8ef4ff14ba83d642adc746d5df39))
* add windows / mac version of blackmagic sdk ([fd6d83c](https://github.com/Fuse-Technical-Group/pydecklink/commit/fd6d83c2bab22b4922313c765f0e8418fef10cf1))
* add Windows CI workflow and resolve midl.exe via find_program ([9a5f785](https://github.com/Fuse-Technical-Group/pydecklink/commit/9a5f785445a63880dbb87b6ee033f3567116df04))
* add Windows platform support for DeckLink SDK builds ([6b7066c](https://github.com/Fuse-Technical-Group/pydecklink/commit/6b7066c031f154a4bea44699c45be6fa1b311bb6))
* add Windows SDK directory override for scikit-build ([63bc698](https://github.com/Fuse-Technical-Group/pydecklink/commit/63bc69824e833327d11c00450a8e0d5e7f36d0b7))
* add windows support ([80c5ce5](https://github.com/Fuse-Technical-Group/pydecklink/commit/80c5ce5ed738bd00381c548cadf77ecf54b713d1))
* enable manual triggering of Windows CI workflow ([460ecd8](https://github.com/Fuse-Technical-Group/pydecklink/commit/460ecd85d92f91779578c3beb8803ea6cb1d2a87))
* **examples:** add detect_signals script ([023dd1c](https://github.com/Fuse-Technical-Group/pydecklink/commit/023dd1c0d1e088965ad7deb1b34ac44ebb6b5436))
* **examples:** add detect_signals script ([3078ec7](https://github.com/Fuse-Technical-Group/pydecklink/commit/3078ec7f0139d07ef71aa7aff6e7f2557723710a))
* replace monotonic_raw_us with steady_clock_us for time measurement ([5a3a4c4](https://github.com/Fuse-Technical-Group/pydecklink/commit/5a3a4c4d591d40802a2f4226c41a1e157d4420b2))
* skip Linux container tests on Windows platform ([08657cf](https://github.com/Fuse-Technical-Group/pydecklink/commit/08657cf185445027b1b6fb262490cf19d58738ab))
* **types:** commit nanobind-generated stub for Pylance ([512dca1](https://github.com/Fuse-Technical-Group/pydecklink/commit/512dca116cc7fa90fe9cff742a12862c8652e36d))
* **types:** commit nanobind-generated stub for Pylance ([ecb0500](https://github.com/Fuse-Technical-Group/pydecklink/commit/ecb0500dae9d87f4da72821bc66467e4201fc589))
* **win:** warn on COM STA/MTA apartment conflict ([1631575](https://github.com/Fuse-Technical-Group/pydecklink/commit/16315752f1f248d388fd594acde6968a42806081))


### Fixed

* **bindings:** add missing nanobind string type caster include ([4835fcc](https://github.com/Fuse-Technical-Group/pydecklink/commit/4835fccec9e38bedcba81bdc6b382f6f40f0ad30))
* **ci:** run all unit tests in ci-linux, matching ci-windows ([e8101ef](https://github.com/Fuse-Technical-Group/pydecklink/commit/e8101ef83ff9ed73a69a64520044cc8224d9dcc1))
* clock_us docs ([baa0775](https://github.com/Fuse-Technical-Group/pydecklink/commit/baa0775139aa65d23764b49abb3531681680eee0))
* **gitignore:** restore whitelist pattern for vendored SDK headers ([413f7ca](https://github.com/Fuse-Technical-Group/pydecklink/commit/413f7cafc271365581803c950423de2898f1f276))
* **lint:** exclude generated stub from ruff rules ([2dc5018](https://github.com/Fuse-Technical-Group/pydecklink/commit/2dc5018a43b2de54ae29c314ae9490faa41d0dc9))
* **mypy:** suppress nanobind stubgen errors in generated stub ([f789d08](https://github.com/Fuse-Technical-Group/pydecklink/commit/f789d0842d19ba493b50936de2eb9ac033910f74))
* post-extraction cleanup for devcontainer and hardware tests ([eef5c16](https://github.com/Fuse-Technical-Group/pydecklink/commit/eef5c160088c2fcd90fc625683fff9982af65f1d))
* ruff errors ([6de48cf](https://github.com/Fuse-Technical-Group/pydecklink/commit/6de48cf42cd80e7cbe7e5f5cf3b1471f9f6581c3))
* **test:** guard _has_decklink() for no-SDK builds ([fae2554](https://github.com/Fuse-Technical-Group/pydecklink/commit/fae25540aafa526863f278072b826354741ad3d1))
* **test:** use device 0 and 2 for SDI loopback pair ([ea6ffc5](https://github.com/Fuse-Technical-Group/pydecklink/commit/ea6ffc538722d05feca6fd407bdb18e0e082a6c2))
* **test:** wrap long docstring line to pass ruff E501 ([ced9a12](https://github.com/Fuse-Technical-Group/pydecklink/commit/ced9a1220e292280b096a1ed08aa12a89772d42d))
* **types:** regenerate stub from clean main and exclude from ruff format ([0ee4299](https://github.com/Fuse-Technical-Group/pydecklink/commit/0ee4299ecdbd81ec43f0ae35cd2dcd4a849cf995))
* use nb::sig to define platform independent signature meaning _bindings.pyi is same on any platform ([dd52821](https://github.com/Fuse-Technical-Group/pydecklink/commit/dd52821bed011b77f8f6be95ea9338ced0721519))

## [0.1.18](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.17...v0.1.18) (2026-03-25)


### Added

* **allocator:** accept Python callables for custom alloc/free ([3871501](https://github.com/Fuse-Technical-Group/pyntv2/commit/387150142fcda44675b764bf97f969fe1edbab3b))
* **allocator:** accept Python callables for custom alloc/free ([d7f1a5f](https://github.com/Fuse-Technical-Group/pyntv2/commit/d7f1a5f28c34b106347d8756814cb2f639fd0656))

## [0.1.17](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.16...v0.1.17) (2026-03-25)


### Fixed

* **examples:** reduce passthrough pre-roll from 60 to 3 frames ([717b664](https://github.com/Fuse-Technical-Group/pyntv2/commit/717b664c9b15d9a8885c9709627cebb3f3af8c73))
* **examples:** reduce passthrough pre-roll from 60 to 3 frames ([e30ff2a](https://github.com/Fuse-Technical-Group/pyntv2/commit/e30ff2a625c0b1829af977f0551eb3956efd1233))

## [0.1.16](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.15...v0.1.16) (2026-03-25)


### Added

* **allocator:** add custom video buffer allocator for GPU DMA ([b73f935](https://github.com/Fuse-Technical-Group/pyntv2/commit/b73f935024b74556680e3973ff649c9d4953d51b))
* **allocator:** custom video buffer allocator for GPU DMA ([ed5a00b](https://github.com/Fuse-Technical-Group/pyntv2/commit/ed5a00b13e8933677b37f0e9b562bcb684d3efec))

## [0.1.15](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.14...v0.1.15) (2026-03-25)


### Added

* **device:** add display mode query and validation methods ([adef7c3](https://github.com/Fuse-Technical-Group/pyntv2/commit/adef7c32da2050e4d8c360686fd0154ce7bdac6e))
* **device:** add display mode query methods ([d1c6ee8](https://github.com/Fuse-Technical-Group/pyntv2/commit/d1c6ee8aad44eb721f39a9972d8178e471521734))
* **device:** add display mode query methods ([d8ec255](https://github.com/Fuse-Technical-Group/pyntv2/commit/d8ec2552d12a778a27dedb75d7a9c16cce412476))
* **format:** add get_mode_frame_duration for native frame rate ([6afd424](https://github.com/Fuse-Technical-Group/pyntv2/commit/6afd4240f1be11861667acd18648f358847bbe7d))
* **format:** add get_mode_frame_duration for native frame rate access ([225ec95](https://github.com/Fuse-Technical-Group/pyntv2/commit/225ec955e20a0982c6beaec0756a52178b163b87))
* **stubs:** generate .pyi type stubs for pydecklink._bindings ([132c1c7](https://github.com/Fuse-Technical-Group/pyntv2/commit/132c1c7bee6a7e060727646c6715e0a5480ba478))

## [0.1.14](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.13...v0.1.14) (2026-03-25)


### Fixed

* **pydecklink:** fix UAF in frame data views and add missing accessors ([9d0bc81](https://github.com/Fuse-Technical-Group/pyntv2/commit/9d0bc811242c356c5d80991f9097a6c61a30fef5))
* **pydecklink:** fix UAF in frame data views, add CaptureFrameRef.data ([f91872f](https://github.com/Fuse-Technical-Group/pyntv2/commit/f91872fb3ec7531c877f7eacea28e7243cbb4c6c))

## [0.1.13](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.12...v0.1.13) (2026-03-25)


### Added

* **pydecklink:** add output frame pool and capture timing instrumentation ([fa22c46](https://github.com/Fuse-Technical-Group/pyntv2/commit/fa22c46b32f698d85b6d1fb085963e3ce337e94b))
* **pydecklink:** zero-copy capture, profile management, passthrough ([b502003](https://github.com/Fuse-Technical-Group/pyntv2/commit/b502003dc0dbfe07a3c21a49aaa80de4f8cf1861))


### Fixed

* **devcontainer:** add ldconfig for Desktop Video libs ([bc287ac](https://github.com/Fuse-Technical-Group/pyntv2/commit/bc287ac2c90448aa11ae2d58e07aad4304bc0bc6))

## [0.1.12](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.11...v0.1.12) (2026-03-25)


### Added

* DeckLink passthrough example and integration tests ([e1a16fa](https://github.com/Fuse-Technical-Group/pyntv2/commit/e1a16fae85e7e4c6800d589266dcb9430045214b))
* **examples:** add DeckLink SDI passthrough example ([f86e886](https://github.com/Fuse-Technical-Group/pyntv2/commit/f86e886e7af88587ebb144537964e6356a9b02d8))


### Fixed

* **build:** forward DECKLINK_SDK_DIR to CMake for isolated builds ([b88227d](https://github.com/Fuse-Technical-Group/pyntv2/commit/b88227dcd96dfdcd0de0ffa015dbdd10d8acdf6d))
* **build:** forward DECKLINK_SDK_DIR to CMake for isolated builds ([71319b9](https://github.com/Fuse-Technical-Group/pyntv2/commit/71319b91b6914510207acf480400fe81e709545a))
* **devcontainer:** mount all Desktop Video binaries from host ([80d1285](https://github.com/Fuse-Technical-Group/pyntv2/commit/80d1285020f2b4c3a018229e85f05b593413834b))
* **devcontainer:** mount all Desktop Video binaries from host lib64 ([d87585c](https://github.com/Fuse-Technical-Group/pyntv2/commit/d87585c555dea663a598522d3ac5a22b1b8a8c54))
* **devcontainer:** use community fish feature and correct lib64 path ([ee74c82](https://github.com/Fuse-Technical-Group/pyntv2/commit/ee74c82bf9a4057d5e926a794b164c80be6c5645))
* **devcontainer:** use community fish feature and correct lib64 path ([4f85260](https://github.com/Fuse-Technical-Group/pyntv2/commit/4f85260033ee9bab93e78b5e32ff63d05e6cb035))

## [0.1.11](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.10...v0.1.11) (2026-03-25)


### Added

* add video output and capture input bindings ([e6a1192](https://github.com/Fuse-Technical-Group/pyntv2/commit/e6a1192a8ce9417860b9d70d4b84618ce9c34d3f))
* **input:** add video capture bindings ([0ed736f](https://github.com/Fuse-Technical-Group/pyntv2/commit/0ed736f25730a2f6f4919c6bfcc97711ee3f71ff))
* **output:** add synchronous and scheduled video output bindings ([e2fac75](https://github.com/Fuse-Technical-Group/pyntv2/commit/e2fac751d82c92b0685862a06bdda757af76bbb3))

## [0.1.10](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.9...v0.1.10) (2026-03-25)


### Added

* bind DeckLink SDK enums, device, and format helpers ([14d2d33](https://github.com/Fuse-Technical-Group/pyntv2/commit/14d2d33d28e3c8762762473e7ebbdf1a164d514f))


### Fixed

* **ci:** skip SDK-dependent tests when built without DeckLink headers ([4495711](https://github.com/Fuse-Technical-Group/pyntv2/commit/449571173e0e5a68876642d34a9c7e8437aeac96))

## [0.1.9](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.8...v0.1.9) (2026-03-25)


### Added

* build foundation — pydecklink scaffold and devcontainer ([e2e5237](https://github.com/Fuse-Technical-Group/pyntv2/commit/e2e52379d561ff7ea275c6fb376ad98af5998502))
* **build:** replace pyntv2 build config with pydecklink ([441f421](https://github.com/Fuse-Technical-Group/pyntv2/commit/441f421ad303c7321f0be17af9b5da96fa5692d4))


### Fixed

* **build:** remove unused noqa directive in pydecklink __init__ ([fa868bf](https://github.com/Fuse-Technical-Group/pyntv2/commit/fa868bf7637d0248979e0000e1c6afaf657d97c1))
* **ci:** update ci-linux for pydecklink build ([c7851de](https://github.com/Fuse-Technical-Group/pyntv2/commit/c7851de74a5e7a0b3c363f9a34ebff22f75537c4))

## [0.1.8](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.7...v0.1.8) (2026-03-24)


### Added

* reliability engineering (Spec §9) ([0f44b4d](https://github.com/Fuse-Technical-Group/pyntv2/commit/0f44b4d61a009cd7e522e0cbf89b9a86d99bfcda))


### Fixed

* **test:** exclude warmup drops from dropped-frame assertions ([372bf7e](https://github.com/Fuse-Technical-Group/pyntv2/commit/372bf7e20dc3209fed4eb288b6edd83ae206798c))
* **test:** mark container environment tests as hardware ([fb565e1](https://github.com/Fuse-Technical-Group/pyntv2/commit/fb565e14420b3e88b333236f876038bae793b7e0))
* **test:** release stream ownership in probe finally blocks ([216173f](https://github.com/Fuse-Technical-Group/pyntv2/commit/216173f25a0fc7c3c710421bb48a5909908cc2b4))
* **test:** upgrade integration tests to 4K/60 and fix SDI loopback assertion ([0bb3117](https://github.com/Fuse-Technical-Group/pyntv2/commit/0bb3117e8c4c7bc54621f99e103faee00ab7ddd9))

## [0.1.7](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.6...v0.1.7) (2026-03-24)


### Fixed

* **docs:** merge adjacent blockquotes to fix MD028 ([73479f6](https://github.com/Fuse-Technical-Group/pyntv2/commit/73479f6e83376505f6d799daf684718e47ce0a4d))
* **docs:** merge adjacent blockquotes to fix MD028 lint violation ([bf70117](https://github.com/Fuse-Technical-Group/pyntv2/commit/bf70117352389e630342c4de7853a8503b36b239))

## [0.1.6](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.5...v0.1.6) (2026-03-24)


### Fixed

* **build:** request SABIModule so nanobind actually enables stable ABI ([cf837ef](https://github.com/Fuse-Technical-Group/pyntv2/commit/cf837ef151addd485c424e97690878e29069b548))
* **build:** request SABIModule so nanobind enables stable ABI ([51e2ddc](https://github.com/Fuse-Technical-Group/pyntv2/commit/51e2ddc10409d55902a6d6f6892a6492d1f4916c))

## [0.1.5](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.4...v0.1.5) (2026-03-24)


### Added

* 4K/60 DMA throughput benchmark ([72486bd](https://github.com/Fuse-Technical-Group/pyntv2/commit/72486bdc00103f88ec9ab0083c80f3f842d7fef7))
* add device_id and display_name properties to Card ([3cf6817](https://github.com/Fuse-Technical-Group/pyntv2/commit/3cf6817f01e7c641f2db2e9a1824e9fd16feb4e1))
* **bindings:** add device_id and display_name properties to Card ([ca4b19c](https://github.com/Fuse-Technical-Group/pyntv2/commit/ca4b19cc5bb9aee5dca0c96031604be04bf83469))


### Fixed

* **build:** enable abi3 wheel tag for Python 3.12+ compatibility ([5698fbe](https://github.com/Fuse-Technical-Group/pyntv2/commit/5698fbea2373e9542c1b56aed037b2f5591a676d))

## [0.1.4](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.3...v0.1.4) (2026-03-24)


### Fixed

* **devcontainer:** add sudo and fix .claude volume ownership ([79dd390](https://github.com/Fuse-Technical-Group/pyntv2/commit/79dd3904e4726f06f1955cf1f200bebf9ba4116d))

## [0.1.3](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.2...v0.1.3) (2026-03-24)


### Fixed

* document 32-bit DMA constraint, remove GPU RDMA, fix buffer lock test ([1148853](https://github.com/Fuse-Technical-Group/pyntv2/commit/11488539a9dcf0c3e2400f1d4b35a444f6bc65c2))
* **test:** use page-aligned buffer in DMA buffer lock test ([bf271a1](https://github.com/Fuse-Technical-Group/pyntv2/commit/bf271a118a750c3f60f17a9827db79fe0554781e))

## [0.1.2](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.1...v0.1.2) (2026-03-24)


### Added

* **bind:** add device ownership and improve autocirculate diagnostics ([5969edb](https://github.com/Fuse-Technical-Group/pyntv2/commit/5969edbd15efb74f2be1357dd9a25439d47e8f4a))
* **bindings:** add format metadata helpers (width, height, fps) ([6f38874](https://github.com/Fuse-Technical-Group/pyntv2/commit/6f388745c35f923e031b29bdec5fec06f2f663c1))
* **bindings:** expose transferred_frame on Transfer ([1090802](https://github.com/Fuse-Technical-Group/pyntv2/commit/1090802f00c2d13d77ffb9cc50ed6830ad993bb0))
* **bindings:** release GIL on blocking calls and bind output VBI ([d6d0442](https://github.com/Fuse-Technical-Group/pyntv2/commit/d6d044213f977819d29ba8c36ddaa99a49cda234))
* integration blockers — GIL release, output VBI, format metadata, transfer status ([38b8841](https://github.com/Fuse-Technical-Group/pyntv2/commit/38b8841c39781194324b336eef2b9b9132e4fbff))
* **scripts:** add PCI card reset script for DMA timeout recovery ([cd12a07](https://github.com/Fuse-Technical-Group/pyntv2/commit/cd12a07d9f37e98112194214443a12c8f033d2de))


### Fixed

* **devcontainer:** add CAP_SYS_ADMIN for capture DMA ([4c33a08](https://github.com/Fuse-Technical-Group/pyntv2/commit/4c33a084336f90624399f3200e15a6ef5ca22160))
* **devcontainer:** add CAP_SYS_RAWIO for capture DMA ([1110f45](https://github.com/Fuse-Technical-Group/pyntv2/commit/1110f4574921a909db7acb7cd3b675c56b474988))
* **devcontainer:** drop --privileged in favor of --userns=keep-id ([96edafe](https://github.com/Fuse-Technical-Group/pyntv2/commit/96edafe43e13eb95ede7e78e070cb783068ec9c7))
* **devcontainer:** use privileged mode and set memlock in Dockerfile ([5a41762](https://github.com/Fuse-Technical-Group/pyntv2/commit/5a41762774df3a86f295c85e12d48a8ca9b52d49))
* **dma:** require page-aligned buffers and improve resource cleanup ([ca6c7c7](https://github.com/Fuse-Technical-Group/pyntv2/commit/ca6c7c7dea3c41331d283ab1a3358d85b7c3d9c7))
* **test:** add DMA buffer locking to integration loopback test ([b63a4ab](https://github.com/Fuse-Technical-Group/pyntv2/commit/b63a4ab5493d0169bf580f2062fe219503a6f00b))
* **test:** compare only active frame region in loopback integrity tests ([4d83447](https://github.com/Fuse-Technical-Group/pyntv2/commit/4d83447b67ce5182cdca647d2b8118b26df82ba0))
* **tests:** correct capture DMA probe and format detection test ([9ab9840](https://github.com/Fuse-Technical-Group/pyntv2/commit/9ab9840d8df4366465a759e6b7c805909afb4f66))
* **tests:** skip integration tests when capture DMA is denied ([e998e6d](https://github.com/Fuse-Technical-Group/pyntv2/commit/e998e6d7d7302385af4e25c71b26c7a83e120647))

## [0.1.1](https://github.com/Fuse-Technical-Group/pyntv2/compare/v0.1.0...v0.1.1) (2026-03-19)


### Added

* **card:** bind CNTV2Card with full Phase 1 API surface ([3ad8c96](https://github.com/Fuse-Technical-Group/pyntv2/commit/3ad8c9684a6eb8041d69322879280b1e7223d70a))
* **enums:** bind 10 NTV2 enums with Pythonic names ([5ecb3fa](https://github.com/Fuse-Technical-Group/pyntv2/commit/5ecb3fac66662d6569b074c1a1e2504bf32cb395))
* **routing:** add route_capture and route_playout convenience helpers ([2953b22](https://github.com/Fuse-Technical-Group/pyntv2/commit/2953b22e41e5c47705534d77ba02293cdd6fd7d5))
* **transfer:** bind AUTOCIRCULATE_TRANSFER and AUTOCIRCULATE_STATUS ([8b3a797](https://github.com/Fuse-Technical-Group/pyntv2/commit/8b3a79727cf8ec041f63652405a18edf7ed03f77))


### Fixed

* **devcontainer:** move UV_INSTALL_DIR to sh invocation ([b22806d](https://github.com/Fuse-Technical-Group/pyntv2/commit/b22806d02895b2703d940890c0c15572d007dc5f))
* **devcontainer:** move UV_INSTALL_DIR to sh invocation ([f05f328](https://github.com/Fuse-Technical-Group/pyntv2/commit/f05f328e5e339de2c0808c3399cca8460aeee38e))
* **lint:** disable MD012/MD022 for release-please compatibility ([6682878](https://github.com/Fuse-Technical-Group/pyntv2/commit/668287866c8cf5a5d8bab7f14e308002248c2435))

## Changelog
