#!/usr/bin/env bash
pkill -f "stores.run_all" 2>/dev/null; pkill -f "stores.server:app_from_env" 2>/dev/null
pkill -f "uvicorn app.main" 2>/dev/null; pkill -f "voice.worker" 2>/dev/null
pkill -f "agent_profile.serve" 2>/dev/null; pkill -f "cloudflared tunnel" 2>/dev/null
pkill -f "next dev" 2>/dev/null; pkill -f "next-server" 2>/dev/null
echo stopped
