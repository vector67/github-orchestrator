#!/bin/sh
set -u

test_build_inputs="app tests public config index.html vite.config.mjs babel.config.mjs package-lock.json .env.development"
kept_test_builds=10

clone() {
	if [ "$(uname)" = Darwin ]; then
		cp -cR "$1" "$2"
	else
		cp -R --reflink=auto "$1" "$2"
	fi
}

clone_node_modules() {
	frontend=$1
	main_frontend="$MAIN_CHECKOUT/frontend"
	[ ! -e "$frontend/node_modules" ] &&
		[ "$main_frontend/node_modules/.package-lock.json" -nt "$main_frontend/package-lock.json" ] &&
		cmp -s "$frontend/package-lock.json" "$main_frontend/package-lock.json" || return 1
	clone "$main_frontend/node_modules" "$frontend/node_modules" && touch "$frontend/node_modules/.package-lock.json" && echo "cloned node_modules from the main checkout" && return 0
	rm -rf "$frontend/node_modules"
	return 1
}

stored_test_build() {
	key=$(cd "$1" && find $test_build_inputs -type f -print0 2>/dev/null | sort -z | xargs -0 shasum | shasum | cut -c1-16)
	echo "$SHARED_CACHE/dist-tests/$key"
}

restore_test_build() {
	frontend=$1
	stored=$(stored_test_build "$frontend")
	[ -e "$stored/.built-for-tests" ] || return 1
	rm -rf "$frontend/dist-tests"
	clone "$stored" "$frontend/dist-tests" && touch "$frontend/dist-tests/.built-for-tests" &&
		echo "reused the test build of these sources from another worktree"
}

store_test_build() {
	frontend=$1
	stored=$(stored_test_build "$frontend")
	store=$(dirname "$stored")
	mkdir -p "$store"
	[ -e "$stored" ] || { clone "$frontend/dist-tests" "$stored.$$" && mv "$stored.$$" "$stored"; }
	ls -1t "$store" | tail -n +$((kept_test_builds + 1)) | while read -r old; do rm -rf "${store:?}/$old"; done
}

durations() {
	seconds=.pytest_cache/v/forked_run/seconds
	[ -e "$seconds" ] || [ ! -e "$MAIN_CHECKOUT/$seconds" ] || {
		mkdir -p "$(dirname "$seconds")" && cp "$MAIN_CHECKOUT/$seconds" "$seconds"
	}
}

case "${1:-}" in
clone_node_modules | restore_test_build | store_test_build) "$1" "$2" ;;
durations) durations ;;
*)
	echo "usage: $0 clone_node_modules|restore_test_build|store_test_build <frontend> | durations" >&2
	exit 2
	;;
esac
