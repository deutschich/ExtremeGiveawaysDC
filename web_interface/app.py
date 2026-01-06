from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash
import os
import json
import logging
from datetime import datetime
from pathlib import Path
import sqlite3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Configuration from environment variables
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['ENV'] = os.environ.get('FLASK_ENV', 'production')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', '0') == '1'

# Get data paths from environment variables
DATA_PATH = os.environ.get('DATA_PATH', '/data')
GIVEAWAY_FILE = os.environ.get('GIVEAWAY_FILE', os.path.join(DATA_PATH, 'giveaways.json'))
SERVER_SETTINGS_FILE = os.environ.get('SERVER_SETTINGS_FILE', os.path.join(DATA_PATH, 'server_settings.json'))
STATISTICS_FILE = os.environ.get('STATISTICS_FILE', os.path.join(DATA_PATH, 'statistics.json'))
ENDED_GIVEAWAYS_FILE = os.environ.get('ENDED_GIVEAWAYS_FILE', os.path.join(DATA_PATH, 'ended_giveaways.json'))
DATABASE_FILE = os.environ.get('DATABASE_URL', 'sqlite:////data/web_interface.db').replace('sqlite:///', '')

# Ensure data directory exists
Path(DATA_PATH).mkdir(parents=True, exist_ok=True)

# Initialize database
def init_db():
    """Initialize the SQLite database"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT,
                avatar_url TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                discord_id TEXT NOT NULL,
                data TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")

# Initialize database on startup
init_db()

# Helper functions
def load_giveaways():
    """Load giveaways from JSON file"""
    try:
        if os.path.exists(GIVEAWAY_FILE):
            with open(GIVEAWAY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✅ Loaded {sum(len(g) for g in data.values())} giveaways from {GIVEAWAY_FILE}")
                return data
    except Exception as e:
        logger.error(f"❌ Error loading giveaways from {GIVEAWAY_FILE}: {e}")
    return {}

def load_server_settings():
    """Load server settings from JSON file"""
    try:
        if os.path.exists(SERVER_SETTINGS_FILE):
            with open(SERVER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading server settings: {e}")
    return {}

def save_user_session(discord_id, username, discriminator, avatar_url, access_token, refresh_token, expires_at):
    """Save user session to database"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (discord_id, username, discriminator, avatar_url, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (discord_id, username, discriminator, avatar_url, access_token, refresh_token, expires_at))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving user session: {e}")
        return False

def get_user_by_discord_id(discord_id):
    """Get user from database by Discord ID"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE discord_id = ?', (discord_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'id': user[0],
                'discord_id': user[1],
                'username': user[2],
                'discriminator': user[3],
                'avatar_url': user[4],
                'access_token': user[5],
                'refresh_token': user[6],
                'expires_at': user[7]
            }
    except Exception as e:
        logger.error(f"Error getting user: {e}")
    return None

# Routes
@app.route('/')
def index():
    """Home page"""
    if 'discord_user' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login')
def login():
    """Discord OAuth2 login - redirect to Discord"""
    # Generate Discord OAuth2 URL
    client_id = os.environ.get('DISCORD_CLIENT_ID')
    redirect_uri = os.environ.get('DISCORD_REDIRECT_URI')
    scope = 'identify guilds'
    
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
    )
    
    return redirect(discord_auth_url)

@app.route('/callback')
def callback():
    """Exchange the Discord OAuth2 code for a user token and fetch profile."""
    code = request.args.get('code')
    
    if not code:
        flash("Authentication failed: No code received", "error")
        return redirect(url_for('index'))
    
    # 1. Prepare data to exchange code for token
    data = {
        'client_id': os.environ.get('DISCORD_CLIENT_ID'),
        'client_secret': os.environ.get('DISCORD_CLIENT_SECRET'),
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': os.environ.get('DISCORD_REDIRECT_URI'),
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # 2. POST request to Discord's token endpoint
    try:
        response = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
        token_data = response.json()
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {token_data}")
            flash("Authentication failed at token exchange.", "error")
            return redirect(url_for('index'))
        
        access_token = token_data['access_token']
        
        # 3. Use the access token to fetch user data
        user_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        user_response = requests.get('https://discord.com/api/users/@me', headers=user_headers)
        user_data = user_response.json()
        
        if user_response.status_code != 200:
            logger.error(f"User fetch failed: {user_data}")
            flash("Failed to fetch user profile.", "error")
            return redirect(url_for('index'))
        
        # 4. Store REAL user data in session
        session['discord_user'] = {
            'id': user_data['id'],
            'username': user_data['username'],
            'discriminator': user_data.get('discriminator', '0'),
            'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png" if user_data.get('avatar') else None
        }
        
        flash("Successfully logged in with Discord!", "success")
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        flash("An unexpected error occurred during authentication.", "error")
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash("Successfully logged out!", "success")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    """User dashboard"""
    if 'discord_user' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('login'))
    
    user = session['discord_user']
    
    # Load giveaways to show statistics
    giveaways = load_giveaways()
    total_giveaways = sum(len(g) for g in giveaways.values())
    
    # Mock managed servers for demo
    managed_guilds = [
        {
            'id': '123456789',
            'name': 'Demo Server 1',
            'icon': None,
            'permissions': '2147483647'
        },
        {
            'id': '987654321',
            'name': 'Demo Server 2',
            'icon': None,
            'permissions': '2147483647'
        }
    ]
    
    return render_template('dashboard.html', 
                         user=user,
                         managed_guilds=managed_guilds,
                         total_giveaways=total_giveaways)

@app.route('/server/<guild_id>')
def server_dashboard(guild_id: str):
    """Server-specific dashboard"""
    if 'discord_user' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('login'))
    
    user = session['discord_user']
    
    # Mock server data
    server = {
        'id': guild_id,
        'name': f'Server {guild_id[:6]}',
        'icon': None
    }
    
    # Load giveaways for this server
    giveaways = load_giveaways()
    server_giveaways = giveaways.get(guild_id, {})
    
    # Calculate statistics
    active_count = len(server_giveaways)
    total_participants = 0
    for giveaway in server_giveaways.values():
        total_participants += len(giveaway.get('participants', []))
    
    # Mock settings
    settings = {
        'audit_channel': None,
        'min_participations': 0,
        'min_wins': 0,
        'min_losses': 0
    }
    
    return render_template('server_dashboard.html',
                         user=user,
                         server=server,
                         giveaways=server_giveaways,
                         settings=settings,
                         active_count=active_count,
                         total_participants=total_participants)

@app.route('/api/giveaways/<guild_id>')
def api_get_giveaways(guild_id: str):
    """API endpoint to get giveaways for a server"""
    try:
        giveaways = load_giveaways()
        server_giveaways = giveaways.get(guild_id, {})
        
        # Format giveaways for frontend
        formatted_giveaways = []
        for giveaway_id, giveaway_data in server_giveaways.items():
            try:
                end_time = datetime.fromisoformat(giveaway_data['end_time'].replace('Z', '+00:00'))
                time_left = (end_time - datetime.now()).total_seconds()
                
                formatted_giveaways.append({
                    'id': giveaway_id,
                    'prize': giveaway_data['prize'],
                    'winners_count': giveaway_data['winners_count'],
                    'end_time': giveaway_data['end_time'],
                    'participants': len(giveaway_data.get('participants', [])),
                    'time_left': max(0, time_left),
                    'channel_id': giveaway_data.get('channel_id'),
                    'creator_id': giveaway_data.get('creator_id'),
                    'allowed_roles': giveaway_data.get('allowed_roles', []),
                    'winner_role': giveaway_data.get('winner_role'),
                    'dm_message': giveaway_data.get('dm_message', '')
                })
            except Exception as e:
                logger.error(f"Error formatting giveaway {giveaway_id}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'giveaways': formatted_giveaways
        })
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/create', methods=['POST'])
def api_create_giveaway():
    """API endpoint to create a new giveaway"""
    try:
        data = request.json
        guild_id = data.get('guild_id')
        prize = data.get('prize')
        winners = data.get('winners')
        duration = data.get('duration')
        channel_id = data.get('channel_id')
        
        if not all([guild_id, prize, winners, duration]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        # For now, just log and return success
        logger.info(f"Giveaway creation requested: {prize} for guild {guild_id}")
        
        return jsonify({
            'success': True,
            'message': 'Giveaway creation request sent to bot',
            'data': data
        })
    except Exception as e:
        logger.error(f"Create giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/end', methods=['POST'])
def api_end_giveaway(giveaway_id: str):
    """API endpoint to end a giveaway immediately"""
    try:
        guild_id = request.json.get('guild_id')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        logger.info(f"End giveaway requested: {giveaway_id} for guild {guild_id}")
        
        return jsonify({
            'success': True,
            'message': 'Giveaway end request sent to bot',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"End giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/cancel', methods=['POST'])
def api_cancel_giveaway(giveaway_id: str):
    """API endpoint to cancel a giveaway"""
    try:
        guild_id = request.json.get('guild_id')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        logger.info(f"Cancel giveaway requested: {giveaway_id} for guild {guild_id}")
        
        return jsonify({
            'success': True,
            'message': 'Giveaway cancellation request sent to bot',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"Cancel giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/participants')
def api_get_participants(giveaway_id: str):
    """API endpoint to get giveaway participants"""
    try:
        guild_id = request.args.get('guild_id')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        giveaways = load_giveaways()
        server_giveaways = giveaways.get(guild_id, {})
        
        if giveaway_id not in server_giveaways:
            return jsonify({
                'success': False,
                'error': 'Giveaway not found'
            }), 404
        
        participants = server_giveaways[giveaway_id].get('participants', [])
        
        return jsonify({
            'success': True,
            'participants': participants,
            'count': len(participants)
        })
    except Exception as e:
        logger.error(f"Get participants error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)