#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROFILE=${S31_PROFILE:-production}
JOBS=${S31_BUILD_JOBS:-8}

NUTTX_SOURCE=${S31_NUTTX_SOURCE:-"${PROJECT_ROOT}/nuttx"}
APPS_SOURCE=${S31_APPS_SOURCE:-"${PROJECT_ROOT}/nuttx-apps"}

CONFIG_FILE="${PROJECT_ROOT}/platform/boards/esp32s31-core-function-board/${PROFILE}.conf"
BUILD_DIR=${S31_OUT_DIR:-"${PROJECT_ROOT}/out/esp32s31-${PROFILE}"}
HOST_TOOLS_BIN="${PROJECT_ROOT}/out/host-tools/bin"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Unknown ESP32-S31 profile: ${PROFILE}" >&2
  exit 2
fi

if [[ -f "${PROJECT_ROOT}/tmp/esp-idf-clean/export.sh" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/tmp/esp-idf-clean/export.sh"
fi

if [[ -z "${IDF_PATH:-}" ]]; then
  echo "ESP-IDF environment not found; set IDF_PATH or provide tmp/esp-idf-clean" >&2
  exit 2
fi

python3 "${PROJECT_ROOT}/platform/tools/verify_f0_dependencies.py" \
  --root "${PROJECT_ROOT}"

if [[ -d "${PROJECT_ROOT}/.venv-nuttx/bin" ]]; then
  export PATH="${PROJECT_ROOT}/.venv-nuttx/bin:${PATH}"
fi

if ! command -v genromfs >/dev/null 2>&1; then
  GENROMFS_ARCHIVE="${PROJECT_ROOT}/out/host-tools/genromfs-0.5.2.tar.gz"
  GENROMFS_SOURCE="${PROJECT_ROOT}/out/host-tools/genromfs-0.5.2"
  mkdir -p "${HOST_TOOLS_BIN}" "${GENROMFS_SOURCE}"
  if [[ ! -f "${GENROMFS_ARCHIVE}" ]]; then
    curl --fail --location \
      https://artifacts.px4.io/toolchain/genromfs-0.5.2.tar.gz \
      --output "${GENROMFS_ARCHIVE}"
  fi
  echo "30f37fc734572c1dbaa2504585bc23ba6b8fd7df767ae7155995b2ca0ebed960  ${GENROMFS_ARCHIVE}" \
    | shasum -a 256 --check
  tar -xzf "${GENROMFS_ARCHIVE}" -C "${GENROMFS_SOURCE}" \
    --strip-components=1
  cc -O2 -Wall -DVERSION=\"0.5.2\" \
    "${GENROMFS_SOURCE}/genromfs.c" -o "${HOST_TOOLS_BIN}/genromfs"
  export PATH="${HOST_TOOLS_BIN}:${PATH}"
fi

HAL_SOURCE=${S31_HAL_SOURCE:-"${PROJECT_ROOT}/deps/esp-hal-3rdparty"}

for source_dir in "${NUTTX_SOURCE}" "${APPS_SOURCE}" \
                  "${HAL_SOURCE}"; do
  if [[ ! -d "${source_dir}" ]]; then
    echo "Required source directory not found: ${source_dir}" >&2
    echo "Run git submodule update --init --recursive to restore sources." >&2
    exit 2
  fi
done
export ESP_HAL_3RDPARTY_LOCAL="${HAL_SOURCE}"

# The NuttX CMake integration patches mbedTLS only when it clones the HAL.
# A local HAL checkout must be prepared explicitly, while preserving any
# unrelated work in the nested mbedTLS repository.
MBEDTLS_SOURCE="${HAL_SOURCE}/components/mbedtls/mbedtls"
MBEDTLS_PATCH_DIR="${HAL_SOURCE}/nuttx/patches/components/mbedtls/mbedtls"
MBEDTLS_PATCH_2="${MBEDTLS_PATCH_DIR}/0002-mbedtls_add_prefix_to_macro.patch"
if ! git -C "${MBEDTLS_SOURCE}" apply --reverse --check \
     "${MBEDTLS_PATCH_2}" 2>/dev/null; then
  for patch_name in 0001-mbedtls_add_prefix.patch \
                    0002-mbedtls_add_prefix_to_macro.patch; do
    patch_file="${MBEDTLS_PATCH_DIR}/${patch_name}"
    if git -C "${MBEDTLS_SOURCE}" apply --check "${patch_file}"; then
      git -C "${MBEDTLS_SOURCE}" apply "${patch_file}"
    elif git -C "${MBEDTLS_SOURCE}" apply --reverse --check \
         "${patch_file}" 2>/dev/null; then
      : # This patch is present and the following patch is not present yet.
    else
      echo "Cannot apply or verify mbedTLS patch: ${patch_file}" >&2
      exit 2
    fi
  done
fi

cmake -S "${NUTTX_SOURCE}" -B "${BUILD_DIR}" -G Ninja \
  -DBOARD_CONFIG=esp32s31-core-function-board:external \
  -DNUTTX_APPS_DIR="${APPS_SOURCE}" \
  -DNUTTX_CONFIG_FILE="${CONFIG_FILE}" \
  -DESP_PHY_LIB_REPO="${IDF_PATH}/components/esp_phy/lib" \
  -DESP_COEX_LIB_REPO="${IDF_PATH}/components/esp_coex/lib" \
  -DESP_WIFI_LIB_REPO="${IDF_PATH}/components/esp_wifi/lib"

cmake --build "${BUILD_DIR}" -j "${JOBS}"

cp "${PROJECT_ROOT}/deps/f0.lock.json" \
  "${BUILD_DIR}/dependency-manifest.json"

(
  cd "${BUILD_DIR}"
  shasum -a 256 nuttx.bin appfs.img > images.sha256
)

echo "ESP32-S31 ${PROFILE} build: ${BUILD_DIR}"
