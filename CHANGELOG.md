# Changelog

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
