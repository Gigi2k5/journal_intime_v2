from flask import Flask,send_file, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
from io import BytesIO
import os
from collections import Counter
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()  # Charger les variables depuis .env

SECRET_KEY_CRYPTO = os.environ.get('SECRET_CRYPTO_KEY')

if not SECRET_KEY_CRYPTO:
    raise RuntimeError("La clé secrète de chiffrement n'est pas définie. Vérifie ton fichier .env")

fernet = Fernet(SECRET_KEY_CRYPTO)



# Configuration de l'application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'un_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Initialiser LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."

# --- Association many-to-many entre JournalEntry et Tag ---
entry_tags = db.Table('entry_tags',
    db.Column('entry_id', db.Integer, db.ForeignKey('journal_entry.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)


# ------------------- MODÈLES -------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    
    # Préférences utilisateur
    theme = db.Column(db.String(20), default="light")  # 'light' ou 'dark'
    font = db.Column(db.String(50), default="default")  # ex : 'serif', 'sans-serif', etc.
    

    # Relation avec les entrées de journal
    entries = db.relationship('JournalEntry', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"User('{self.first_name}', '{self.email}')"

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f"Tag('{self.nom}')"


class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    _texte = db.Column("texte", db.LargeBinary, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    humeur = db.Column(db.String(10), nullable=True)

    # Relation many-to-many avec Tag
    tags = db.relationship('Tag', secondary=entry_tags, backref=db.backref('entries', lazy='dynamic'))

    @property
    def texte(self):
        try:
            return fernet.decrypt(self._texte).decode()
        except Exception:
            return self._texte.decode() if isinstance(self._texte, bytes) else str(self._texte)

    @texte.setter
    def texte(self, value):
        self._texte = fernet.encrypt(value.encode())

    def __repr__(self):
        return f"JournalEntry(id={self.id}, user_id={self.user_id}, humeur={self.humeur})"

class MessageContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return f"Message de {self.nom} ({self.email})"

# ------------------- FONCTIONS UTILITAIRES -------------------

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # Changement ici

def get_user_entries(user_id):
    """Récupère les entrées de journal de l'utilisateur, triées par date décroissante."""
    return JournalEntry.query.filter_by(user_id=user_id).order_by(JournalEntry.date_created.desc()).all()

def paginate_by_words(entries, page, words_per_page):
    """
    Pagination personnalisée par nombre de mots
    
    Args:
        entries: Liste des entrées de journal
        page: Numéro de page actuelle
        words_per_page: Nombre de mots par page
        
    Returns:
        Tuple contenant (entries_paginées, info_pagination)
    """
    # Concaténer tous les mots de toutes les entrées
    all_words = []
    all_entries_dict = {}
    
    for entry in entries:
        # Stocker l'entrée pour référence
        all_entries_dict[entry.id] = entry
        # Diviser le texte en mots et ajouter chaque mot avec l'ID de son entrée
        words = entry.texte.split()
        for word in words:
            all_words.append((entry.id, word))
    
    # Calculer le nombre total de pages
    total_words = len(all_words)
    total_pages = max(1, (total_words + words_per_page - 1) // words_per_page)
    
    # S'assurer que la page demandée est valide
    page = max(1, min(page, total_pages))
    
    # Sélectionner les mots pour la page actuelle
    start_idx = (page - 1) * words_per_page
    end_idx = min(start_idx + words_per_page, total_words)
    page_words = all_words[start_idx:end_idx]
    
    # Regrouper les mots par entrée
    grouped_entries = {}
    for entry_id, word in page_words:
        if entry_id not in grouped_entries:
            grouped_entries[entry_id] = {
                'entry': all_entries_dict[entry_id],
                'words': []
            }
        grouped_entries[entry_id]['words'].append(word)
    
    # Créer l'objet pagination
    pagination = {
        'page': page,
        'pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1,
        'next_num': page + 1
    }
    
    return list(grouped_entries.values()), pagination

# ------------------- ROUTES -------------------

# --- Routes de pages générales ---

@app.route('/')
def home():
    prenom = "Copain/Copine"
    # Liste des citations
    citations = [
        "Le succès, c'est tomber sept fois, se relever huit.",
        "La vie est 10% ce qui nous arrive et 90% comment nous réagissons.",
        "La meilleure façon de prédire l'avenir, c'est de l'inventer.",
        "Celui qui n'a pas d'objectifs vit un voyage sans destination.",
        "Ne regarde pas l'horloge ; fais ce qu'elle fait. Continue."
    ]
    
    # Sélectionner une citation en fonction de la seconde actuelle
    current_second = datetime.datetime.now().second
    citation = citations[current_second % len(citations)]
    
    return render_template("home.html", prenom_utilisateurs=prenom, citation_du_jour=citation)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]

        nouveau_message = MessageContact(nom=name, email=email)
        db.session.add(nouveau_message)
        db.session.commit()

        flash(f"Merci {name}, votre message a été enregistré.", "success")
        return redirect(url_for('contact'))

    return render_template("contact.html")

@app.route('/messages')
def afficher_messages():
    messages = MessageContact.query.all()
    return render_template('messages.html', messages=messages)



# --- Routes d'authentification ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Cet email est déjà utilisé.", "error")
            return redirect(url_for('register'))

        new_user = User(first_name=first_name, last_name=last_name, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("Inscription réussie ! Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Connexion réussie !", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Identifiants incorrects.", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Déconnexion réussie.", "success")
    return redirect(url_for('home'))

# --- Routes utilisateur ---

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user

    # Compter les humeurs
    humeurs = [entry.humeur for entry in user.entries if entry.humeur]
    compteur_humeurs = Counter(humeurs)

    labels = list(compteur_humeurs.keys()) if compteur_humeurs else []
    counts = list(compteur_humeurs.values()) if compteur_humeurs else []


    return render_template(
        'dashboard.html',
        user=user,
        humeurs_labels=labels,
        humeurs_counts=counts
    )

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        theme = request.form.get('theme')
        font = request.form.get('font')
        
        current_user.theme = theme
        current_user.font = font
        db.session.commit()
        flash("Préférences mises à jour avec succès.", "success")
        return redirect(url_for('settings'))

    return render_template("settings.html", user=current_user)

@app.route('/export_txt')
@login_required
def export_txt():
    entries = get_user_entries(current_user.id)

    contenu = ""
    for entry in entries[::-1]:  # Affiche les plus anciennes d’abord
        date = entry.date_created.strftime('%d/%m/%Y %H:%M')
        contenu += f"=== {date} ===\n{entry.texte}\n\n"

    buffer = BytesIO()
    buffer.write(contenu.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="mon_journal.txt",
        mimetype='text/plain'
    )
# --- Routes du journal ---

# Helper pour récupérer ou créer un tag
def get_or_create_tag(nom):
    nom = nom.strip()
    if not nom:
        return None
    tag = Tag.query.filter_by(nom=nom).first()
    if not tag:
        tag = Tag(nom=nom)
        db.session.add(tag)
        db.session.commit()
    return tag

# Route journal avec filtre tag ajouté
@app.route('/journal', methods=['GET', 'POST'])
@login_required
def journal():
    if request.method == 'POST':
        texte = request.form.get('texte')
        humeur = request.form.get('humeur')
        tags_str = request.form.get('tags', '')
        if texte and texte.strip():
            nouvelle_entree = JournalEntry(texte=texte, user_id=current_user.id, humeur=humeur)
            db.session.add(nouvelle_entree)
            db.session.commit()

            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
            for tag_nom in tags_list:
                tag = get_or_create_tag(tag_nom)
                if tag:
                    nouvelle_entree.tags.append(tag)
            db.session.commit()

            from random import choice
            citations = [
                "Continue comme ça, tu fais du super travail ! 😊",
                "Chaque mot compte, bravo ! 💪",
                "Écrire, c'est déjà avancer.",
                "Belle humeur aujourd'hui, ça se sent ! 🌟",
                "Prends soin de toi à travers tes mots."
            ]
            flash(choice(citations), "success")
        else:
            flash("Veuillez écrire quelque chose...", "error")
        return redirect(url_for('journal'))

    mot_cle = request.args.get('mot_cle', '').strip()
    date_str = request.args.get('date', '').strip()
    tag_filtre = request.args.get('tag', '').strip()

    # Filtrage par tag (en SQL)
    if tag_filtre:
        tag_obj = Tag.query.filter_by(nom=tag_filtre).first()
        if tag_obj:
            requete = tag_obj.entries.filter(JournalEntry.user_id == current_user.id)
        else:
            requete = JournalEntry.query.filter_by(user_id=current_user.id).filter(False)  # aucun résultat
    else:
        requete = JournalEntry.query.filter_by(user_id=current_user.id)

    # Filtrage par date (en SQL)
    if date_str:
        try:
            date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            requete = requete.filter(db.func.date(JournalEntry.date_created) == date)
        except ValueError:
            flash("Format de date invalide.", "error")

    # Récupérer toutes les entrées filtrées par tag et date
    entries = requete.order_by(JournalEntry.date_created.desc()).all()

    # Filtrage par mot clé en Python (sur texte déchiffré)
    if mot_cle:
        mot_cle_lower = mot_cle.lower()
        entries = [e for e in entries if mot_cle_lower in e.texte.lower()]

    # Pagination par mots (comme avant)
    page = request.args.get('page', 1, type=int)
    per_page_words = 200
    entries_paginated, pagination = paginate_by_words(entries, page, per_page_words)

    return render_template(
        'journal.html',
        entries=entries_paginated,
        pagination=pagination,
        tag_filtre=tag_filtre
    )


@app.route('/journal/edit/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('journal'))

    if request.method == 'POST':
        texte = request.form.get('texte')
        humeur = request.form.get('humeur')
        tags_str = request.form.get('tags', '')
        if texte and texte.strip():
            entry.texte = texte
            entry.humeur = humeur

            # Mise à jour tags
            entry.tags.clear()
            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
            for tag_nom in tags_list:
                tag = get_or_create_tag(tag_nom)
                if tag:
                    entry.tags.append(tag)

            db.session.commit()
            flash("Entrée mise à jour avec succès.", "success")
            return redirect(url_for('journal'))
        else:
            flash("Veuillez écrire quelque chose...", "error")

    return render_template("edit_journal.html", entry=entry)

@app.route('/journal/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('journal'))

    db.session.delete(entry)
    db.session.commit()
    flash("Entrée supprimée avec succès.", "success")
    return redirect(url_for('journal'))


# --- Initialisation et lancement ---

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)