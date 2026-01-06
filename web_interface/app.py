from flask import Flask, render_template, redirect, url_for, session, request, jsonify, flash
from flask_discord import DiscordOAuth2Session, requires_authorization, Unauthorized
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration from environment variables
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
app.config['ENV'] = os.environ.get('FLASK_ENV', 'production')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', '0') == '1'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'true') == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get('SESSION_COOKIE_HTTPONLY', 'true') == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')

# Discord OAuth2 Configuration
app.config['DISCORD_CLIENT_ID'] = os.environ.get('DISCORD_CLIENT_ID')
app.config['DISCORD_CLIENT_SECRET'] = os.environ.get('DISCORD_CLIENT_SECRET')
app.config['DISCORD_REDIRECT_URI'] = os.environ.get('DISCORD_REDIRECT_URI')
app.config['DISCORD_BOT_TOKEN'] = os.environ.get('DISCORD_BOT_TOKEN')

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///data/web_interface.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
try:
    discord_oauth = DiscordOAuth2Session(app)
except Exception as e:
    logger.error(f"Failed to initialize Discord OAuth: {e}")
    discord_oauth = None

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Get data paths from environment variables or use defaults
DATA_PATH = os.environ.get('DATA_PATH', '/data')
GIVEAWAY_FILE = os.environ.get('GIVEAWAY_FILE', os.path.join(DATA_PATH, 'giveaways.json'))
SERVER_SETTINGS_FILE = os.environ.get('SERVER_SETTINGS_FILE', os.path.join(DATA_PATH, 'server_settings.json'))
STATISTICS_FILE = os.environ.get('STATISTICS_FILE', os.path.join(DATA_PATH, 'statistics.json'))
ENDED_GIVEAWAYS_FILE = os.environ.get('ENDED_GIVEAWAYS_FILE', os.path.join(DATA_PATH, 'ended_giveaways.json'))

# Ensure data directory exists
Path(DATA_PATH).mkdir(parents=True, exist_ok=True)

# Models (unchanged)
class UserSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(100), unique=True, nullable=False)
    access_token = db.Column(db.String(500), nullable=False)
    refresh_token = db.Column(db.String(500))
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class ServerCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(100), unique=True, nullable=False)
    server_data = db.Column(db.Text, nullable=False)
    cached_at = db.Column(db.DateTime, default=datetime.utcnow)

# Helper functions
def load_giveaways() -> Dict:
    """Load giveaways from JSON file"""
    try:
        if os.path.exists(GIVEAWAY_FILE):
            with open(GIVEAWAY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading giveaways: {e}")
    return {}

def load_server_settings() -> Dict:
    """Load server settings from JSON file"""
    try:
        if os.path.exists(SERVER_SETTINGS_FILE):
            with open(SERVER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading server settings: {e}")
    return {}

def get_user_guilds(access_token: str) -> List[Dict]:
    """Get user's guilds from Discord API"""
    try:
        headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        # This would be an async call in production
        # For now, we'll return mock data
        return []
    except Exception as e:
        logger.error(f"Error fetching user guilds: {e}")
        return []

def get_bot_guilds() -> List[Dict]:
    """Get guilds where bot is present"""
    try:
        # This should call your bot's API or read from cache
        # For now, we'll read from the giveaway files
        giveaways = load_giveaways()
        bot_guilds = []
        
        for guild_id in giveaways.keys():
            bot_guilds.append({
                'id': guild_id,
                'name': f'Server {guild_id}',
                'icon': None,
                'permissions': '2147483647',  # Administrator permissions
                'features': []
            })
        
        return bot_guilds
    except Exception as e:
        logger.error(f"Error getting bot guilds: {e}")
        return []

def get_managed_guilds(user_guilds: List[Dict], bot_guilds: List[Dict]) -> List[Dict]:
    """Get guilds where user has admin permissions and bot is present"""
    managed_guilds = []
    
    for user_guild in user_guilds:
        # Check if user has administrator permissions (0x8)
        permissions = int(user_guild.get('permissions', 0))
        has_admin = (permissions & 0x8) == 0x8
        
        # Check if bot is in this guild
        bot_in_guild = any(bot_guild['id'] == user_guild['id'] for bot_guild in bot_guilds)
        
        if has_admin and bot_in_guild:
            managed_guilds.append(user_guild)
    
    return managed_guilds

# Routes
@app.route('/')
def index():
    """Home page"""
    if discord_oauth and discord_oauth.authorized:
        user = discord_oauth.fetch_user()
        return render_template('dashboard.html', user=user)
    return render_template('index.html')

@app.route('/login')
def login():
    """Discord OAuth2 login"""
    if not discord_oauth:
        flash("Discord OAuth is not configured properly", "error")
        return redirect(url_for('index'))
    
    return discord_oauth.create_session(scope=['identify', 'guilds'])

@app.route('/callback')
def callback():
    """OAuth2 callback"""
    if not discord_oauth:
        flash("Discord OAuth is not configured properly", "error")
        return redirect(url_for('index'))
    
    try:
        discord_oauth.callback()
        user = discord_oauth.fetch_user()
        
        # Store user session
        session['discord_user'] = {
            'id': user.id,
            'username': user.username,
            'discriminator': user.discriminator,
            'avatar': user.avatar_url if user.avatar_url else None
        }
        
        flash("Successfully logged in!", "success")
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        flash("Failed to authenticate with Discord", "error")
        return redirect(url_for('index'))

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    flash("Successfully logged out!", "success")
    return redirect(url_for('index'))

@app.route('/dashboard')
@requires_authorization
def dashboard():
    """User dashboard"""
    user = discord_oauth.fetch_user()
    
    # Get user's guilds
    user_guilds = get_user_guilds(discord_oauth.get_oauth_token())
    
    # Get bot's guilds
    bot_guilds = get_bot_guilds()
    
    # Get managed guilds
    managed_guilds = get_managed_guilds(user_guilds, bot_guilds)
    
    return render_template('dashboard.html', 
                         user=user,
                         managed_guilds=managed_guilds,
                         total_guilds=len(managed_guilds))

@app.route('/server/<guild_id>')
@requires_authorization
def server_dashboard(guild_id: str):
    """Server-specific dashboard"""
    user = discord_oauth.fetch_user()
    
    # Verify user has permissions in this guild
    user_guilds = get_user_guilds(discord_oauth.get_oauth_token())
    user_guild = next((g for g in user_guilds if g['id'] == guild_id), None)
    
    if not user_guild:
        flash("You don't have access to this server", "error")
        return redirect(url_for('dashboard'))
    
    # Check permissions
    permissions = int(user_guild.get('permissions', 0))
    has_admin = (permissions & 0x8) == 0x8
    
    if not has_admin:
        flash("You need administrator permissions in this server", "error")
        return redirect(url_for('dashboard'))
    
    # Load giveaways for this server
    giveaways = load_giveaways()
    server_giveaways = giveaways.get(guild_id, {})
    
    # Load server settings
    server_settings = load_server_settings()
    settings = server_settings.get(guild_id, {})
    
    # Calculate statistics
    active_count = len(server_giveaways)
    total_participants = 0
    for giveaway in server_giveaways.values():
        total_participants += len(giveaway.get('participants', []))
    
    return render_template('server_dashboard.html',
                         user=user,
                         server=user_guild,
                         giveaways=server_giveaways,
                         settings=settings,
                         active_count=active_count,
                         total_participants=total_participants)

@app.route('/api/giveaways/<guild_id>')
@requires_authorization
def api_get_giveaways(guild_id: str):
    """API endpoint to get giveaways for a server"""
    try:
        giveaways = load_giveaways()
        server_giveaways = giveaways.get(guild_id, {})
        
        # Format giveaways for frontend
        formatted_giveaways = []
        for giveaway_id, giveaway_data in server_giveaways.items():
            try:
                end_time = datetime.fromisoformat(giveaway_data['end_time'])
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
@requires_authorization
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
        
        # Here you would call your bot's API to create the giveaway
        # For now, we'll just return success
        return jsonify({
            'success': True,
            'message': 'Giveaway creation request sent',
            'data': data
        })
    except Exception as e:
        logger.error(f"Create giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/edit', methods=['POST'])
@requires_authorization
def api_edit_giveaway(giveaway_id: str):
    """API endpoint to edit a giveaway"""
    try:
        data = request.json
        field = data.get('field')
        value = data.get('value')
        guild_id = data.get('guild_id')
        
        if not all([field, value, guild_id]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        # Here you would call your bot's API to edit the giveaway
        return jsonify({
            'success': True,
            'message': f'Giveaway {field} updated',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"Edit giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/end', methods=['POST'])
@requires_authorization
def api_end_giveaway(giveaway_id: str):
    """API endpoint to end a giveaway immediately"""
    try:
        guild_id = request.json.get('guild_id')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        # Here you would call your bot's API to end the giveaway
        return jsonify({
            'success': True,
            'message': 'Giveaway ended successfully',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"End giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/cancel', methods=['POST'])
@requires_authorization
def api_cancel_giveaway(giveaway_id: str):
    """API endpoint to cancel a giveaway"""
    try:
        guild_id = request.json.get('guild_id')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        # Here you would call your bot's API to cancel the giveaway
        return jsonify({
            'success': True,
            'message': 'Giveaway cancelled successfully',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"Cancel giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/reroll', methods=['POST'])
@requires_authorization
def api_reroll_giveaway(giveaway_id: str):
    """API endpoint to reroll a giveaway"""
    try:
        data = request.json
        guild_id = data.get('guild_id')
        winners_count = data.get('winners_count')
        
        if not guild_id:
            return jsonify({
                'success': False,
                'error': 'Missing guild_id'
            }), 400
        
        # Here you would call your bot's API to reroll the giveaway
        return jsonify({
            'success': True,
            'message': 'Giveaway rerolled successfully',
            'giveaway_id': giveaway_id
        })
    except Exception as e:
        logger.error(f"Reroll giveaway error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/giveaway/<giveaway_id>/participants')
@requires_authorization
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

@app.route('/api/server/<guild_id>/channels')
@requires_authorization
def api_get_channels(guild_id: str):
    """API endpoint to get server channels"""
    try:
        # Here you would fetch channels from Discord API or your bot
        # For now, return mock data
        channels = [
            {'id': '1', 'name': 'general', 'type': 'text'},
            {'id': '2', 'name': 'giveaways', 'type': 'text'},
            {'id': '3', 'name': 'announcements', 'type': 'text'}
        ]
        
        return jsonify({
            'success': True,
            'channels': channels
        })
    except Exception as e:
        logger.error(f"Get channels error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/server/<guild_id>/roles')
@requires_authorization
def api_get_roles(guild_id: str):
    """API endpoint to get server roles"""
    try:
        # Here you would fetch roles from Discord API or your bot
        # For now, return mock data
        roles = [
            {'id': '1', 'name': '@everyone'},
            {'id': '2', 'name': 'Admin'},
            {'id': '3', 'name': 'Giveaway Winner'}
        ]
        
        return jsonify({
            'success': True,
            'roles': roles
        })
    except Exception as e:
        logger.error(f"Get roles error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Error handlers
@app.errorhandler(Unauthorized)
def redirect_unauthorized(e):
    flash("Please login to access this page", "warning")
    return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)