from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import string
import random
import os
from functools import wraps
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anil123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///splitly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    code = db.Column(db.String(6), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    creator = db.relationship('User', backref='created_groups')
    
    def __repr__(self):
        return f'<Group {self.name}>'

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    group = db.relationship('Group', backref='members')
    user = db.relationship('User', backref='group_memberships')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    split_members = db.Column(db.Text, nullable=False)  # Comma-separated user IDs
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    group = db.relationship('Group', backref='expenses')
    payer = db.relationship('User', backref='paid_expenses')
    
    def __repr__(self):
        return f'<Expense {self.description}:  {self.amount}>'

class Settlement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    from_user = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_user = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    group = db.relationship('Group', backref='settlements')
    from_user_obj = db.relationship('User', foreign_keys=[from_user], backref='settlements_made')
    to_user_obj = db.relationship('User', foreign_keys=[to_user], backref='settlements_received')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_group_code():
    """Generate a unique 6-character group code"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not Group.query.filter_by(code=code).first():
            return code

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
            name = data.get('name')
            
            # Validate input
            if not email or not password or not name:
                return jsonify({'success': False, 'message': 'All fields are required'})
            
            if len(password) < 6:
                return jsonify({'success': False, 'message': 'Password must be at least 6 characters'})
            
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                return jsonify({'success': False, 'message': 'Email already exists'})
            
            # Create new user
            user = User(
                email=email,
                name=name,
                password_hash=generate_password_hash(password)
            )
            
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            return jsonify({'success': True, 'redirect': url_for('dashboard')})
            
        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {e}")  # For debugging
            return jsonify({'success': False, 'message': 'Registration failed. Please try again.'})
    
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        
            if not email or not password:
                return jsonify({'success': False, 'message': 'Email and password are required'})
        
            user = User.query.filter_by(email=email).first()
        
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            else:
                return jsonify({'success': False, 'message': 'Invalid email or password'})
            
        except Exception as e:
            print(f"Login error: {e}")  # For debugging
            return jsonify({'success': False, 'message': 'Login failed. Please try again.'})
    
    return render_template('auth.html', mode='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_groups = db.session.query(Group).join(GroupMember).filter(
        GroupMember.user_id == current_user.id
    ).all()
    
    return render_template('dashboard.html', groups=user_groups)

@app.route('/create-group', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        description = data.get('description', '')
        
        group = Group(
            name=name,
            description=description,
            code=generate_group_code(),
            created_by=current_user.id
        )
        db.session.add(group)
        db.session.flush()
        
        # Add creator as group member
        member = GroupMember(group_id=group.id, user_id=current_user.id)
        db.session.add(member)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'group_code': group.code,
            'redirect': url_for('group_detail', group_id=group.id)
        })
    
    return render_template('create_group.html')

@app.route('/join-group', methods=['GET', 'POST'])
@login_required
def join_group():
    if request.method == 'POST':
        data = request.get_json()
        code = data.get('code').upper()
        
        group = Group.query.filter_by(code=code).first()
        if not group:
            return jsonify({'success': False, 'message': 'Invalid group code'})
        
        # Check if user is already a member
        existing_member = GroupMember.query.filter_by(
            group_id=group.id, user_id=current_user.id
        ).first()
        
        if existing_member:
            return jsonify({'success': False, 'message': 'You are already a member of this group'})
        
        member = GroupMember(group_id=group.id, user_id=current_user.id)
        db.session.add(member)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'redirect': url_for('group_detail', group_id=group.id)
        })
    
    return render_template('join_group.html')

@app.route('/group/<int:group_id>')
@login_required
def group_detail(group_id):
    group = Group.query.get_or_404(group_id)
    
    # Check if user is a member
    member = GroupMember.query.filter_by(
        group_id=group_id, user_id=current_user.id
    ).first()
    
    if not member:
        flash('You are not a member of this group')
        return redirect(url_for('dashboard'))
    
    expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.date.desc()).all()
    members = db.session.query(User).join(GroupMember).filter(
        GroupMember.group_id == group_id
    ).all()
    
    # Calculate balances
    balances = calculate_group_balances(group_id)
    
    return render_template('group_detail.html', 
                         group=group, 
                         expenses=expenses, 
                         members=members,
                         balances=balances)

@app.route('/add-expense/<int:group_id>', methods=['GET', 'POST'])
@login_required
def add_expense(group_id):
    group = Group.query.get_or_404(group_id)
    
    if request.method == 'POST':
        data = request.get_json()
        
        expense = Expense(
            group_id=group_id,
            description=data.get('description'),
            amount=float(data.get('amount')),
            paid_by=int(data.get('paid_by')),
            date=datetime.now(),
            split_members=','.join(map(str, data.get('split_members', [])))
        )
        
        db.session.add(expense)
        db.session.commit()
        
        return jsonify({'success': True, 'redirect': url_for('group_detail', group_id=group_id)})
    
    # Convert User objects to dictionaries for JSON serialization
    members_query = db.session.query(User).join(GroupMember).filter(
        GroupMember.group_id == group_id
    ).all()
    
    members = [{'id': member.id, 'name': member.name} for member in members_query]
    
    return render_template('add_expense.html', group=group, members=members)

@app.route('/delete-expense/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    try:
        expense = Expense.query.get_or_404(expense_id)
        
        # Check if user is a member of the group
        member = GroupMember.query.filter_by(
            group_id=expense.group_id, user_id=current_user.id
        ).first()
        
        if not member:
            return jsonify({'success': False, 'message': 'You are not authorized to delete this expense'})
        
        group_id = expense.group_id
        db.session.delete(expense)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Expense deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Delete expense error: {e}")
        return jsonify({'success': False, 'message': 'Failed to delete expense'})

@app.route('/settle-up/<int:group_id>')
@login_required
def settle_up(group_id):
    group = Group.query.get_or_404(group_id)
    balances = calculate_group_balances(group_id)
    settlements = calculate_settlements(balances)
    
    members = db.session.query(User).join(GroupMember).filter(
        GroupMember.group_id == group_id
    ).all()
    
    return render_template('settle_up.html', 
                         group=group, 
                         balances=balances,
                         settlements=settlements,
                         members=members)

@app.route('/mark-settled', methods=['POST'])
@login_required
def mark_settled():
    data = request.get_json()
    
    settlement = Settlement(
        group_id=data.get('group_id'),
        from_user=data.get('from_user'),
        to_user=data.get('to_user'),
        amount=float(data.get('amount')),
        date=datetime.now()
    )
    
    db.session.add(settlement)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/download-pdf/<int:group_id>')
@login_required
def download_pdf(group_id):
    try:
        group = Group.query.get_or_404(group_id)
        
        # Check if user is a member
        member = GroupMember.query.filter_by(
            group_id=group_id, user_id=current_user.id
        ).first()
        
        if not member:
            return "Unauthorized", 403
        
        # Get data
        expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.date.desc()).all()
        members = db.session.query(User).join(GroupMember).filter(
            GroupMember.group_id == group_id
        ).all()
        balances = calculate_group_balances(group_id)
        settlements = calculate_settlements(balances)
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2563eb')
        )
        story.append(Paragraph(f"Splitly Pro - {group.name}", title_style))
        story.append(Spacer(1, 20))
        
        # Group Info
        info_style = ParagraphStyle(
            'Info',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=10
        )
        story.append(Paragraph(f"<b>Group Code:</b> {group.code}", info_style))
        if group.description:
            story.append(Paragraph(f"<b>Description:</b> {group.description}", info_style))
        story.append(Paragraph(f"<b>Generated on:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", info_style))
        story.append(Spacer(1, 20))
        
        # Summary
        total_expenses = sum(expense.amount for expense in expenses)
        story.append(Paragraph("<b>Summary</b>", styles['Heading2']))
        story.append(Paragraph(f"Total Expenses: {total_expenses:.2f}", info_style))
        story.append(Paragraph(f"Number of Expenses: {len(expenses)}", info_style))
        story.append(Paragraph(f"Group Members: {len(members)}", info_style))
        story.append(Spacer(1, 20))
        
        # Current Balances
        story.append(Paragraph("<b>Current Balances</b>", styles['Heading2']))
        balance_data = [['Member', 'Balance', 'Status']]
        
        for member in members:
            balance = balances.get(member.id, 0)
            if balance > 0.01:
                status = "Gets back"
                balance_str = f"+ {balance:.2f}"
            elif balance < -0.01:
                status = "Owes"
                balance_str = f"- {abs(balance):.2f}"
            else:
                status = "Settled"
                balance_str = " 0.00"
            
            balance_data.append([member.name, balance_str, status])
        
        balance_table = Table(balance_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
        balance_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(balance_table)
        story.append(Spacer(1, 20))
        
        # Suggested Settlements
        if settlements:
            story.append(Paragraph("<b>Suggested Settlements</b>", styles['Heading2']))
            settlement_data = [['From', 'To', 'Amount']]
            
            for settlement in settlements:
                from_user = next((m for m in members if m.id == settlement['from_user']), None)
                to_user = next((m for m in members if m.id == settlement['to_user']), None)
                
                settlement_data.append([
                    from_user.name if from_user else 'Unknown',
                    to_user.name if to_user else 'Unknown',
                    f" {settlement['amount']:.2f}"
                ])
            
            settlement_table = Table(settlement_data, colWidths=[2*inch, 2*inch, 1.5*inch])
            settlement_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(settlement_table)
            story.append(Spacer(1, 20))
        
        # Expense Details
        if expenses:
            story.append(Paragraph("<b>Expense Details</b>", styles['Heading2']))
            expense_data = [['Date', 'Description', 'Paid By', 'Amount', 'Split Between']]
            
            for expense in expenses:
                split_member_ids = [int(x) for x in expense.split_members.split(',') if x]
                split_names = [m.name for m in members if m.id in split_member_ids]
                
                expense_data.append([
                    expense.date.strftime('%m/%d/%Y'),
                    expense.description[:30] + ('...' if len(expense.description) > 30 else ''),
                    expense.payer.name,
                    f" {expense.amount:.2f}",
                    ', '.join(split_names)[:40] + ('...' if len(', '.join(split_names)) > 40 else '')
                ])
            
            expense_table = Table(expense_data, colWidths=[1*inch, 2*inch, 1.5*inch, 1*inch, 2*inch])
            expense_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(expense_table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        # Create response
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{group.name}_expenses.pdf"'
        
        return response
        
    except Exception as e:
        print(f"PDF generation error: {e}")
        return "Error generating PDF", 500

def calculate_group_balances(group_id):
    """Calculate how much each member owes or is owed"""
    expenses = Expense.query.filter_by(group_id=group_id).all()
    settlements = Settlement.query.filter_by(group_id=group_id).all()
    
    balances = {}
    
    # Calculate from expenses
    for expense in expenses:
        split_members = [int(x) for x in expense.split_members.split(',') if x]
        split_amount = expense.amount / len(split_members)
        
        # Person who paid gets credited
        if expense.paid_by not in balances:
            balances[expense.paid_by] = 0
        balances[expense.paid_by] += expense.amount
        
        # Each person who shared gets debited
        for member_id in split_members:
            if member_id not in balances:
                balances[member_id] = 0
            balances[member_id] -= split_amount
    
    # Subtract settlements
    for settlement in settlements:
        if settlement.from_user not in balances:
            balances[settlement.from_user] = 0
        if settlement.to_user not in balances:
            balances[settlement.to_user] = 0
            
        balances[settlement.from_user] += settlement.amount
        balances[settlement.to_user] -= settlement.amount
    
    return balances

def calculate_settlements(balances):
    """Calculate optimal settlements to minimize transactions"""
    creditors = [(user_id, amount) for user_id, amount in balances.items() if amount > 0.01]
    debtors = [(user_id, -amount) for user_id, amount in balances.items() if amount < -0.01]
    
    settlements = []
    
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)
    
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        creditor_id, credit_amount = creditors[i]
        debtor_id, debt_amount = debtors[j]
        
        settle_amount = min(credit_amount, debt_amount)
        
        if settle_amount > 0.01:
            settlements.append({
                'from_user': debtor_id,
                'to_user': creditor_id,
                'amount': round(settle_amount, 2)
            })
        
        creditors[i] = (creditor_id, credit_amount - settle_amount)
        debtors[j] = (debtor_id, debt_amount - settle_amount)
        
        if creditors[i][1] < 0.01:
            i += 1
        if debtors[j][1] < 0.01:
            j += 1
    
    return settlements

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
