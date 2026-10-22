use_github_api=false
gh_account=null
mcp_config=null
earlier_primer=null
while [ $# -gt 0 ]; do
    case "$1" in
        --behaviour) behaviour=$2; shift ;;
        --config) config=$2; shift ;;
        --work-dir) out=$2; shift ;;
        --use-github-api) use_github_api=true ;;
        --gh-account) gh_account="\"$2\""; shift ;;
        --mcp-config) mcp_config="\"$2\""; shift ;;
        --earlier-primer) IFS= read -r earlier_primer < "$2"; shift ;;
        *) pr=$1 ;;
    esac
    shift
done

for entry in "$out"/* "$out"/.[!.]*; do
    if [ -e "$entry" ]; then
        echo "WorkDirNotEmpty: $out" >&2
        exit 1
    fi
done

witnesses="claimed implementation tests why"
case "$behaviour" in
    clean) folders="$witnesses primer alignment" ;;
    malformed-alignment) folders="$witnesses alignment" ;;
    needs-api | crash) folders= ;;
    hang | partway | partway-then-a-witness-fails) folders=claimed ;;
    *) folders=$witnesses ;;
esac
cwd=$(pwd -P)
set -- "$out"
for folder in $folders; do
    set -- "$@" "$out/$folder"
done
mkdir -p "$@"

printf '{"pr": "%s", "config": "%s", "cwd": "%s", "use_github_api": %s, "gh_account": %s, "mcp_config": %s, "earlier_primer": %s}' \
    "$pr" "$config" "$cwd" "$use_github_api" "$gh_account" "$mcp_config" "$earlier_primer" > "$out/call.json"

finish() {
    printf '%s' "$2" > "$out/$1/output.json"
}

case "$behaviour" in
    needs-api)
        echo "Cannot read acme/widgets locally: the working directory is not a clone of it." >&2
        echo "Confirm reading its 3 changed files over the GitHub API (about 31 API calls) by adding --use-github-api." >&2
        exit 3 ;;
    crash)
        echo "GhFailed: gh pr view failed" >&2
        exit 1 ;;
    hang)
        finish claimed '{"claims": []}'
        sleep 60 ;;
    partway | partway-then-a-witness-fails)
        finish claimed '{"claims": []}'
        mkdir "$out/implementation"
        until [ -e "$out/go-on" ]; do
            if [ -e "$out/die" ]; then
                kill -KILL 0
            fi
            sleep 0.02
        done
        mkdir "$out/tests" "$out/why" ;;
esac
for witness in $witnesses; do
    finish "$witness" '{}'
done
case "$behaviour" in
    clean)
        finish primer '{"witness": "primer", "concepts": [{"name": "Toolbar", "explanation": "The row of buttons.", "concepts": []}]}'
        finish alignment '{"mismatches": [{"rung": "requested"}, {"rung": "claimed"}]}' ;;
    malformed-alignment)
        printf '{not json' > "$out/alignment/output.json" ;;
esac
printf '# Summary\n\nIt does what it says.\n'
echo "Working files: $out"
if [ "$behaviour" = partway-then-a-witness-fails ]; then
    echo "Witnesses failed: why: timed out" >&2
    exit 1
fi
