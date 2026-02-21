#!/bin/bash

# EMAX Trading Engine Control Menu
# This script provides an interactive menu for controlling the trading engine

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Log file
LOG_FILE="$SCRIPT_DIR/trading_engine.log"

# PID file
PID_FILE="$SCRIPT_DIR/engine.pid"


# Ensure logs directory exists
mkdir -p "$SCRIPT_DIR/logs"

# Get configured port and instance ID
PORT=$(python3 -c "import json, os; print(json.load(open(os.path.join('$SCRIPT_DIR', 'config/trading_config.json')))['dashboard'].get('web_port', 8081))" 2>/dev/null || echo "8081")
INSTANCE_ID=$(python3 -c "import json, os; print(json.load(open(os.path.join('$SCRIPT_DIR', 'config/trading_config.json')))['telegram'].get('message_prefix', 'EMAX'))" 2>/dev/null || echo "EMAX")
DIR_NAME=$(basename "$SCRIPT_DIR")

# Define additional colors
BOLD='\033[1m'
PURPLE='\033[0;35m'
CYAN_BOLD='\033[1;36m'


# Function to show header
show_header() {
    clear
    echo -e "${CYAN_BOLD}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN_BOLD}║${NC}       ${GREEN}${BOLD}EMAX Trading Engine Control Panel${NC}              ${CYAN_BOLD}║${NC}"
    echo -e "${CYAN_BOLD}╠════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN_BOLD}║${NC}  ${PURPLE}Instance:${NC} ${INSTANCE_ID}                              ${CYAN_BOLD}║${NC}"
    echo -e "${CYAN_BOLD}║${NC}  ${PURPLE}Dir:${NC}      ${DIR_NAME}                           ${CYAN_BOLD}║${NC}"
    echo -e "${CYAN_BOLD}║${NC}  ${PURPLE}Port:${NC}     ${PORT}                                    ${CYAN_BOLD}║${NC}"
    echo -e "${CYAN_BOLD}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Function to check if engine is running
is_engine_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            # Stale PID file
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

# Function to check if dashboard is running
is_dashboard_running() {
    # Dashboard is integrated with main.py, so check if port $PORT is in use
    if lsof -i :$PORT > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Function to show running processes
show_running_processes() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━ RUNNING PROCESSES ━━━━━━━━━━━━━━━━${NC}"

    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            local cmd=$(ps -p "$pid" -o pid=,comm=,args= 2>/dev/null | head -1)
            echo -e "  ${GREEN}PID $pid:${NC} $cmd (Main Engine)"
        else
            echo -e "  ${RED}PID file exists ($pid) but process is missing${NC}"
        fi
    else
        echo -e "  ${YELLOW}No active engine (no PID file)${NC}"
    fi

    # Also check what's on port $PORT
    local port_pid=$(lsof -ti:$PORT 2>/dev/null || true)
    if [ -n "$port_pid" ]; then
        echo -e "  ${CYAN}Port $PORT:${NC} PID $port_pid (Dashboard)"
    fi

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Function to show status
show_status() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━ STATUS ━━━━━━━━━━━━━━━━━━${NC}"

    if is_engine_running; then
        echo -e "  Engine:    ${GREEN}● RUNNING${NC}"
    else
        echo -e "  Engine:    ${RED}○ STOPPED${NC}"
    fi

    if is_dashboard_running; then
        echo -e "  Dashboard: ${GREEN}● RUNNING${NC} (http://localhost:$PORT)"
    else
        echo -e "  Dashboard: ${RED}○ STOPPED${NC}"
    fi

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Function to start engine
start_engine() {
    echo -e "${YELLOW}Starting EMAX Trading Engine...${NC}"

    if is_engine_running; then
        echo -e "${YELLOW}Engine is already running!${NC}"
        return 1
    fi

    # Wine Python requires DISPLAY to be set (use existing X server)
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:0
    fi

    # Start engine in background
    # NOTE: Wine Python cannot handle file redirects when backgrounded,
    # so we redirect to /dev/null. main.py has its own file logging configured.
    DISPLAY="$DISPLAY" wine python main.py </dev/null >/dev/null 2>&1 &
    echo $! > "$PID_FILE"

    sleep 3

    if is_engine_running; then
        echo -e "${GREEN}✓ Engine started successfully${NC}"
        echo -e "${CYAN}  Dashboard should be available at: http://localhost:$PORT${NC}"
        echo -e "${CYAN}  Logs: $LOG_FILE${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to start engine. Check logs: $LOG_FILE${NC}"
        return 1
    fi
}

# Function to stop engine
stop_engine() {
    echo -e "${YELLOW}Stopping EMAX Trading Engine...${NC}"
    
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Engine is not running (no PID file).${NC}"
        # Cleanup potential stale processes just in case, but warn
        return 0
    fi
    
    local pid=$(cat "$PID_FILE")
    
    # Check if process actually exists
    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}PID file exists but process $pid is gone. Cleaning up.${NC}"
        rm -f "$PID_FILE"
        return 0
    fi

    # Kill process
    kill "$pid" 2>/dev/null
    
    sleep 2
    
    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Engine stopped successfully${NC}"
        rm -f "$PID_FILE"
        return 0
    else
        echo -e "${RED}✗ Failed to stop engine (PID $pid)${NC}"
        return 1
    fi
}

# Function to start dashboard only (if engine has separate dashboard)
start_dashboard() {
    echo -e "${YELLOW}Starting Dashboard...${NC}"
    
    # Note: In EMAX, the dashboard is integrated with main.py
    # This function is for cases where dashboard might be separate
    
    if is_engine_running; then
        echo -e "${CYAN}Dashboard is integrated with the engine.${NC}"
        echo -e "${GREEN}✓ Dashboard available at: http://localhost:$PORT${NC}"
        return 0
    else
        echo -e "${YELLOW}Engine is not running. Starting engine (which includes dashboard)...${NC}"
        start_engine
        return $?
    fi
}

# Function to stop dashboard
stop_dashboard() {
    echo -e "${YELLOW}Stopping Dashboard...${NC}"
    
    # Note: In EMAX, stopping dashboard means stopping the engine
    echo -e "${CYAN}Dashboard is integrated with the engine.${NC}"
    echo -e "${YELLOW}To stop the dashboard, you need to stop the engine.${NC}"
    
    read -p "Stop the engine? (y/n): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        stop_engine
    else
        echo -e "${YELLOW}Dashboard not stopped.${NC}"
    fi
}

# Function to reset (stop, clean logs, start)
reset_engine() {
    echo -e "${YELLOW}Resetting EMAX Trading Engine...${NC}"
    
    # Stop engine
    stop_engine
    
    # Clean logs
    echo -e "${YELLOW}Cleaning log files...${NC}"
    rm -f "$SCRIPT_DIR"/*.log 2>/dev/null
    rm -f "$SCRIPT_DIR"/logs/*.log 2>/dev/null
    echo -e "${GREEN}✓ Logs cleaned${NC}"
    
    # Start engine
    start_engine
}

# Function to restart (stop + start)
restart_engine() {
    echo -e "${YELLOW}Restarting EMAX Trading Engine...${NC}"
    
    # Stop engine
    stop_engine
    
    sleep 2
    
    # Start engine
    start_engine
}

# Function to view logs
view_logs() {
    echo -e "${YELLOW}Viewing logs (Ctrl+C to exit)...${NC}"
    echo ""
    
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo -e "${YELLOW}No log file found at: $LOG_FILE${NC}"
    fi
}

# Function to clean logs
clean_logs() {
    echo -e "${YELLOW}Cleaning log files...${NC}"
    
    rm -f "$SCRIPT_DIR"/*.log 2>/dev/null
    rm -f "$SCRIPT_DIR"/logs/*.log 2>/dev/null
    
    echo -e "${GREEN}✓ All log files cleaned${NC}"
}

# Main menu
show_menu() {
    echo -e "${YELLOW}COMMANDS:${NC}"
    echo ""
    echo -e "  ${GREEN}1${NC}) Start Engine"
    echo -e "  ${RED}2${NC}) Stop Engine"
    echo -e "  ${CYAN}3${NC}) Reset Engine (Stop + Clean Logs + Start)"
    echo ""
    echo -e "  ${GREEN}4${NC}) Start Dashboard"
    echo -e "  ${RED}5${NC}) Stop Dashboard"
    echo ""
    echo -e "  ${BLUE}6${NC}) View Logs (live)"
    echo -e "  ${YELLOW}7${NC}) Clean Logs"
    echo -e "  ${RED}8${NC}) Clean Stalled PID"
    echo -e "  ${PURPLE}9${NC}) Test Trades Open Close 1 Min"
    echo ""
    echo -e "  ${CYAN}0${NC}) Restart Engine & Dashboard"
    echo -e "  ${NC}q${NC}) Exit"
    echo ""
}

# Command line argument handling
if [ $# -gt 0 ]; then
    case "$1" in
        start)
            start_engine
            ;;
        stop)
            stop_engine
            ;;
        reset)
            reset_engine
            ;;
        restart)
            restart_engine
            ;;
        start-dashboard)
            start_dashboard
            ;;
        stop-dashboard)
            stop_dashboard
            ;;
        status)
            show_header
            show_running_processes
            show_status
            ;;
        logs)
            view_logs
            ;;
        clean-logs)
            clean_logs
            ;;
        *)
            echo "Usage: $0 {start|stop|reset|start-dashboard|stop-dashboard|status|logs|clean-logs}"
            exit 1
            ;;
    esac
    exit 0
fi

# Interactive menu loop
while true; do
    show_header
    show_running_processes
    show_status
    show_menu
    
    read -p "Enter choice: " choice
    echo ""
    
    case $choice in
        1)
            start_engine
            ;;
        2)
            stop_engine
            ;;
        3)
            reset_engine
            ;;
        4)
            start_dashboard
            ;;
        5)
            stop_dashboard
            ;;
        6)
            view_logs
            ;;
        7)
            clean_logs
            ;;
        8)
            ./clean_stalled_pid.sh
            ;;
        9)
            ./wine_python.sh scripts/test_multi_asset.py
            ;;
        0)
            restart_engine
            ;;
        q|Q)
            echo -e "${GREEN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please try again.${NC}"
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
done
