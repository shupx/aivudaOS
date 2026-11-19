#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

sdk_dir="${ANDROID_SDK_ROOT:-$HOME/.local/share/aivuda-android}"
tools="$sdk_dir/build-tools/34.0.0"
platform="$sdk_dir/platforms/android-29/android.jar"
ui=../aivudaos/resources/ui
key="${AIVUDA_SIGNING_KEY:-$HOME/.local/share/aivuda-android/development.p12}"

prepare_signing_key() {
    if [[ -n "${AIVUDA_SIGNING_KEY:-}" ]]; then
        : "${AIVUDA_KEY_PASSWORD:?Set the password for the release keystore}"
    elif [[ ! -f "$key" ]]; then
        mkdir -p "$(dirname "$key")"
        (umask 077; keytool -genkeypair -keystore "$key" -storetype PKCS12 \
            -alias aivuda -storepass android -keypass android -keyalg RSA \
            -keysize 2048 -validity 7300 -dname 'CN=Aivuda Local Development')
    fi
    export AIVUDA_KEY_PASSWORD="${AIVUDA_KEY_PASSWORD:-android}"
}

prepare_station_assets() {
    local station_res="$stage/station-res"
    local host="${AIVUDA_STORE_HOST:-}"
    mkdir -p "$stage/assets" "$station_res/xml"
    (cd "$ui" && npm run build:h16 -- --outDir "$stage/assets/panel")

    if [[ -n "${AIVUDA_STORE_CA:-}" ]]; then
        if [[ ! "$host" =~ ^[A-Za-z0-9.-]+$ ]]; then
            printf 'Set AIVUDA_STORE_HOST to the hostname of the store using this CA.\n' >&2
            return 1
        fi
        mkdir -p "$station_res/raw"
        cp "$AIVUDA_STORE_CA" "$station_res/raw/store_ca.crt"
    fi
    {
        printf '%s\n' '<network-security-config>' \
            '  <base-config cleartextTrafficPermitted="true"><trust-anchors><certificates src="system"/></trust-anchors></base-config>'
        if [[ -n "${AIVUDA_STORE_CA:-}" ]]; then
            printf '  <domain-config><domain>%s</domain><trust-anchors><certificates src="@raw/store_ca"/></trust-anchors></domain-config>\n' "$host"
        fi
        printf '%s\n' '</network-security-config>'
    } > "$station_res/xml/panel_network.xml"
}

build_apk() {
    local out="$stage"
    mkdir -p "$out"/{generated,classes,dex}
    "$tools/aapt" package -f -M station/AndroidManifest.xml -I "$platform" \
        --auto-add-overlay -S i18n/locales -S "$stage/resources" -S "$stage/station-res" -A "$stage/assets" \
        --custom-package com.aivuda.h16 -m -J "$out/generated" -F "$out/unsigned.apk"
    javac --release 8 -encoding UTF-8 -cp "$platform" -d "$out/classes" \
        "$out/generated/com/aivuda/h16/R.java" station/*.java
    jar cf "$out/classes.jar" -C "$out/classes" .
    "$tools/d8" --min-api 25 --lib "$platform" --output "$out/dex" "$out/classes.jar"
    (cd "$out/dex" && "$tools/aapt" add "$out/unsigned.apk" classes.dex)
    "$tools/zipalign" -f 4 "$out/unsigned.apk" "$out/aligned.apk"
    "$tools/apksigner" sign --ks "$key" --ks-pass env:AIVUDA_KEY_PASSWORD \
        --out "$out/signed.apk" "$out/aligned.apk"
    "$tools/apksigner" verify --min-sdk-version 25 "$out/signed.apk"
}

stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
prepare_signing_key
mkdir -p "$stage/resources/drawable-nodpi"
cp "$ui/public/aivuda_icon.png" "$stage/resources/drawable-nodpi/"
prepare_station_assets
build_apk

mkdir -p build
mv "$stage/signed.apk" build/aivuda-station.apk
printf 'Built android/build/aivuda-station.apk\n'
