from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from werkzeug.security import check_password_hash
from functools import wraps
from datetime import datetime
import json
import os
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Add a secret key for flash messages

# Data file paths
INVENTORY_FILE = 'inventory.json'
SALES_FOLDER = 'sales'
EXPENSES_FOLDER = 'expenses'
USERS_FILE = 'users.json'

# User Authentication Functions
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def verify_password(username, password):
    users = load_users()
    user = next((u for u in users if u['username'] == username), None)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

# Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Ensure folders exist
def ensure_folders_exist():
    for folder in [SALES_FOLDER, EXPENSES_FOLDER]:
        if not os.path.exists(folder):
            os.makedirs(folder)

# Initialize data structure
def initialize_inventory():
    return {
        'inventory': []
    }

def initialize_daily_file(file_type):
    return {
        file_type: [],
        'daily_summary': {
            'sales_count': 0,
            'sales_amount': 0,
            'profit': 0,
            'expenses': 0
        } if file_type == 'sales' else {}
    }

# Load inventory from file
def load_inventory():
    if os.path.exists(INVENTORY_FILE):
        with open(INVENTORY_FILE, 'r') as f:
            return json.load(f)
    else:
        data = initialize_inventory()
        save_inventory(data)
        return data

# Save inventory to file
def save_inventory(data):
    with open(INVENTORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Get daily file path
def get_daily_file_path(file_type):
    today = datetime.now().strftime('%Y-%m-%d')
    folder = SALES_FOLDER if file_type == 'sales' else EXPENSES_FOLDER
    return os.path.join(folder, f"{today}_{file_type}.json")

# Load daily data
def load_daily_data(file_type):
    file_path = get_daily_file_path(file_type)
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        data = initialize_daily_file(file_type)
        save_daily_data(file_type, data)
        return data

# Save daily data
def save_daily_data(file_type, data):
    file_path = get_daily_file_path(file_type)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# Update daily summary
def update_daily_summary(sales_data):
    # Calculate today's sales
    sales = sales_data['sales']
    sales_amount = sum(sale['total_price'] for sale in sales)
    profit = sum(sale['profit'] for sale in sales)
    
    # Update summary
    sales_data['daily_summary']['sales_count'] = len(sales)
    sales_data['daily_summary']['sales_amount'] = sales_amount
    sales_data['daily_summary']['profit'] = profit
    
    return sales_data

# Get all daily summaries
def get_all_daily_summaries():
    summaries = []
    
    # Get sales summaries
    for filename in os.listdir(SALES_FOLDER):
        if filename.endswith('_sales.json'):
            date = filename.split('_')[0]
            file_path = os.path.join(SALES_FOLDER, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                summary = data.get('daily_summary', {})
                summary['date'] = date
                summaries.append(summary)
    
    # Get expenses for each day
    for summary in summaries:
        date = summary['date']
        expense_file = os.path.join(EXPENSES_FOLDER, f"{date}_expenses.json")
        if os.path.exists(expense_file):
            with open(expense_file, 'r') as f:
                data = json.load(f)
                expenses_amount = sum(expense['amount'] for expense in data.get('expenses', []))
                summary['expenses'] = expenses_amount
        else:
            summary['expenses'] = 0
    
    return sorted(summaries, key=lambda x: x['date'], reverse=True)

# Get recent sales
def get_recent_sales(limit=5):
    all_sales = []
    
    for filename in os.listdir(SALES_FOLDER):
        if filename.endswith('_sales.json'):
            file_path = os.path.join(SALES_FOLDER, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_sales.extend(data.get('sales', []))
    
    return sorted(all_sales, key=lambda x: x['date'], reverse=True)[:limit]

# Get recent expenses
def get_recent_expenses(limit=5):
    all_expenses = []
    
    for filename in os.listdir(EXPENSES_FOLDER):
        if filename.endswith('_expenses.json'):
            file_path = os.path.join(EXPENSES_FOLDER, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_expenses.extend(data.get('expenses', []))
    
    return sorted(all_expenses, key=lambda x: x['date'], reverse=True)[:limit]

# Add expense
def add_expense_record(category, description, amount):
    expenses_data = load_daily_data('expenses')
    
    new_expense = {
        'id': str(uuid.uuid4()),
        'category': category,
        'description': description,
        'amount': float(amount),
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    expenses_data['expenses'].append(new_expense)
    save_daily_data('expenses', expenses_data)
    
    return new_expense

# Find a sale by ID in any sales file
def find_sale_by_id(sale_id):
    for filename in os.listdir(SALES_FOLDER):
        if filename.endswith('_sales.json'):
            file_path = os.path.join(SALES_FOLDER, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                for sale in data.get('sales', []):
                    if sale['id'] == sale_id:
                        return sale, file_path, data
    return None, None, None

# Return items to inventory
def return_items_to_inventory(sale):
    inventory_data = load_inventory()
    
    # Check if this is a regular sale (not a trade-in)
    if sale.get('type') != 'trade_in':
        # Try to find the item in inventory
        item = next((item for item in inventory_data['inventory'] if item['id'] == sale['item_id']), None)
        
        if item:
            # Item exists, increase quantity
            item['quantity'] += sale['quantity']
        else:
            # Item doesn't exist anymore, create a new one
            new_item = {
                'id': sale['item_id'],
                'name': sale['item_name'],
                'category': sale['category'],
                'model_number': sale['model_number'],
                'imei_number': sale.get('imei_number', ''),
                'purchase_price': (sale['total_price'] - sale['profit']) / sale['quantity'],  # Calculate purchase price
                'quantity': sale['quantity'],
                'supplier': 'Returned from sale',
                'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            inventory_data['inventory'].append(new_item)
    
    # If it's a trade-in (negative price), remove it from inventory
    elif sale.get('type') == 'trade_in':
        inventory_data['inventory'] = [item for item in inventory_data['inventory'] 
                                     if item['id'] != sale['item_id']]
    
    save_inventory(inventory_data)

# Login and Logout Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = verify_password(username, password)
        if user:
            session['user'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    ensure_folders_exist()
    
    # Get today's summary
    today_sales_data = load_daily_data('sales')
    today_summary = today_sales_data['daily_summary']
    today_summary['date'] = datetime.now().strftime('%Y-%m-%d')
    
    # Get expenses for today
    today_expenses_data = load_daily_data('expenses')
    expenses_amount = sum(expense['amount'] for expense in today_expenses_data.get('expenses', []))
    today_summary['expenses'] = expenses_amount
    
    # Get recent sales and expenses
    recent_sales = get_recent_sales()
    recent_expenses = get_recent_expenses()
    
    # Get inventory data
    inventory_data = load_inventory()
    
    # Get low stock items (less than 5 quantity)
    low_stock = [item for item in inventory_data['inventory'] if item['quantity'] < 5]
    
    return render_template('index.html',
                           summary=today_summary,
                           recent_sales=recent_sales,
                           recent_expenses=recent_expenses,
                           low_stock=low_stock)

@app.route('/inventory')
@login_required
def inventory():
    ensure_folders_exist()
    inventory_data = load_inventory()
    return render_template('inventory.html', inventory=inventory_data['inventory'])

@app.route('/add_multiple_inventory', methods=['POST'])
@login_required
def add_multiple_inventory():
    ensure_folders_exist()
    inventory_data = load_inventory()
    
    # Get form data
    form_data = request.form
    
    # Process each item
    item_index = 0
    while True:
        # Check if we have more items to process
        item_name_key = f'items[{item_index}][name]'
        if item_name_key not in form_data:
            break
        
        category = form_data[f'items[{item_index}][category]']
        quantity = int(form_data[f'items[{item_index}][quantity]'])
        purchase_price = float(form_data[f'items[{item_index}][purchase_price]'])
        
        # Different fields based on category
        if category == 'Phone':
            imei_number = form_data[f'items[{item_index}][imei_number]']
            model_number = form_data[f'items[{item_index}][model_number]']
            
            # For phones, add one entry per IMEI
            for i in range(quantity):
                new_item = {
                    'id': str(uuid.uuid4()),
                    'name': form_data[f'items[{item_index}][name]'],
                    'category': category,
                    'model_number': model_number,
                    'imei_number': imei_number,
                    'purchase_price': purchase_price,
                    'quantity': 1,
                    'supplier': form_data.get(f'items[{item_index}][supplier]', ''),
                    'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                inventory_data['inventory'].append(new_item)
                
                # Add expense for each phone
                add_expense_record(
                    'Inventory Purchase',
                    f"Phone: {new_item['name']} (Model: {model_number}, IMEI: {imei_number})",
                    purchase_price
                )
        else:
            # For accessories, add as a single entry with quantity
            new_item = {
                'id': str(uuid.uuid4()),
                'name': form_data[f'items[{item_index}][name]'],
                'category': category,
                'model_number': form_data[f'items[{item_index}][model_number]'],
                'imei_number': '',
                'purchase_price': purchase_price,
                'quantity': quantity,
                'supplier': form_data.get(f'items[{item_index}][supplier]', ''),
                'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            inventory_data['inventory'].append(new_item)
            
            # Add expense for accessories (price * quantity)
            add_expense_record(
                'Inventory Purchase',
                f"Accessory: {new_item['name']} (Model: {new_item['model_number']}, Qty: {quantity})",
                purchase_price * quantity
            )
        
        item_index += 1
    
    save_inventory(inventory_data)
    return redirect(url_for('inventory'))

@app.route('/edit_inventory_item/<item_id>', methods=['GET', 'POST'])
@login_required
def edit_inventory_item(item_id):
    inventory_data = load_inventory()
    
    # Find the item
    item_index = next((i for i, item in enumerate(inventory_data['inventory']) 
                      if item['id'] == item_id), None)
    
    if item_index is None:
        flash('Item not found', 'error')
        return redirect(url_for('inventory'))
    
    if request.method == 'POST':
        # Update the item with form data
        item = inventory_data['inventory'][item_index]
        
        item['name'] = request.form['name']
        item['category'] = request.form['category']
        item['model_number'] = request.form['model_number']
        
        if item['category'] == 'Phone':
            item['imei_number'] = request.form['imei_number']
        
        item['purchase_price'] = float(request.form['purchase_price'])
        item['quantity'] = int(request.form['quantity'])
        item['supplier'] = request.form['supplier']
        
        save_inventory(inventory_data)
        flash('Item updated successfully', 'success')
        return redirect(url_for('inventory'))
    
    # GET request - show edit form
    return render_template('edit_inventory.html', item=inventory_data['inventory'][item_index])

@app.route('/delete_inventory_item/<item_id>', methods=['POST'])
@login_required
def delete_inventory_item(item_id):
    inventory_data = load_inventory()
    
    # Find and remove the item
    inventory_data['inventory'] = [item for item in inventory_data['inventory'] 
                                 if item['id'] != item_id]
    
    save_inventory(inventory_data)
    flash('Item deleted successfully', 'success')
    return redirect(url_for('inventory'))

@app.route('/sales')
@login_required
def sales():
    ensure_folders_exist()
    sales_data = load_daily_data('sales')
    inventory_data = load_inventory()
    
    return render_template('sales.html',
                           sales=sales_data['sales'],
                           inventory=inventory_data['inventory'])

@app.route('/add_multiple_sales', methods=['POST'])
@login_required
def add_multiple_sales():
    ensure_folders_exist()
    inventory_data = load_inventory()
    sales_data = load_daily_data('sales')
    
    # Get customer information
    customer_name = request.form['customer_name']
    customer_phone = request.form['customer_phone']
    
    # Get cart data from form
    cart_data = json.loads(request.form['cart_data'])

    # Get trade-in data if available
    trade_in_data = json.loads(request.form.get('trade_in_data', '[]'))
    
    # Get borrowed items data if available
    borrowed_items_data = json.loads(request.form.get('borrowed_items_data', '[]'))
    
    # Process each item in the cart
    sale_items = []
    total_amount = 0
    
    # Process regular sales
    for cart_item in cart_data:
        item_id = cart_item['id']
        quantity = cart_item['quantity']
        selling_price = cart_item['sellingPrice']
        
        # Find the item in inventory
        item = next((item for item in inventory_data['inventory'] if item['id'] == item_id), None)
        
        if item and item['quantity'] >= quantity:
            # Update inventory
            item['quantity'] -= quantity
            
            # Calculate total price and profit
            total_price = selling_price * quantity
            profit = (selling_price - item['purchase_price']) * quantity
            
            # Add sale
            new_sale = {
                'id': str(uuid.uuid4()),
                'customer_name': customer_name,
                'customer_phone': customer_phone,
                'item_id': item_id,
                'item_name': item['name'],
                'category': item['category'],
                'model_number': item['model_number'],
                'imei_number': item.get('imei_number', ''),
                'quantity': quantity,
                'unit_price': selling_price,
                'total_price': total_price,
                'profit': profit,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'type': 'regular'
            }
            
            sales_data['sales'].append(new_sale)
            sale_items.append(new_sale)
            total_amount += total_price
    
    # Process trade-ins (add to inventory)
    for trade_in in trade_in_data:
        # Add the trade-in item to inventory
        new_inventory_item = {
            'id': str(uuid.uuid4()),
            'name': trade_in['name'],
            'category': 'Phone',  # Assuming trade-ins are phones
            'model_number': trade_in['model_number'],
            'imei_number': trade_in['imei_number'],
            'purchase_price': float(trade_in['trade_in_value']),
            'quantity': 1,
            'supplier': 'Trade-in',
            'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        inventory_data['inventory'].append(new_inventory_item)
        
        # Record the trade-in as a special type of sale (negative amount)
        trade_in_sale = {
            'id': str(uuid.uuid4()),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'item_id': new_inventory_item['id'],
            'item_name': trade_in['name'],
            'category': 'Phone',
            'model_number': trade_in['model_number'],
            'imei_number': trade_in['imei_number'],
            'quantity': 1,
            'unit_price': -float(trade_in['trade_in_value']),  # Negative because it's money going out
            'total_price': -float(trade_in['trade_in_value']),
            'profit': 0,  # Profit will be realized when the trade-in is sold
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'trade_in'
        }
        
        sales_data['sales'].append(trade_in_sale)
        sale_items.append(trade_in_sale)
        total_amount -= float(trade_in['trade_in_value'])
        
        # Add expense for the trade-in
        add_expense_record(
            'Trade-in Purchase',
            f"Trade-in Phone: {trade_in['name']} (Model: {trade_in['model_number']}, IMEI: {trade_in['imei_number']})",
            float(trade_in['trade_in_value'])
        )
    
    # Process borrowed items (add to inventory and sell immediately)
    for borrowed_item in borrowed_items_data:
        # Add the borrowed item to inventory
        new_inventory_item = {
            'id': str(uuid.uuid4()),
            'name': borrowed_item['name'],
            'category': borrowed_item['category'],
            'model_number': borrowed_item['model_number'],
            'imei_number': '',
            'purchase_price': float(borrowed_item['purchase_price']),
            'quantity': int(borrowed_item['quantity']),
            'supplier': 'Borrowed',
            'date_added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        inventory_data['inventory'].append(new_inventory_item)
        
        # Add expense for the borrowed item
        add_expense_record(
            'Borrowed Item Purchase',
            f"Borrowed {borrowed_item['category']}: {borrowed_item['name']} (Model: {borrowed_item['model_number']})",
            float(borrowed_item['purchase_price']) * int(borrowed_item['quantity'])
        )
        
        # Sell the borrowed item immediately
        selling_price = float(borrowed_item['selling_price'])
        quantity = int(borrowed_item['quantity'])
        total_price = selling_price * quantity
        profit = (selling_price - float(borrowed_item['purchase_price'])) * quantity
        
        # Update inventory (reduce quantity to 0)
        new_inventory_item['quantity'] = 0
        
        # Record the sale
        borrowed_sale = {
            'id': str(uuid.uuid4()),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'item_id': new_inventory_item['id'],
            'item_name': borrowed_item['name'],
            'category': borrowed_item['category'],
            'model_number': borrowed_item['model_number'],
            'imei_number': '',
            'quantity': quantity,
            'unit_price': selling_price,
            'total_price': total_price,
            'profit': profit,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'borrowed_and_sold'
        }
        
        sales_data['sales'].append(borrowed_sale)
        sale_items.append(borrowed_sale)
        total_amount += total_price
    
    # Update daily summary
    sales_data = update_daily_summary(sales_data)
    
    # Save all data
    save_inventory(inventory_data)
    save_daily_data('sales', sales_data)
    
    # Generate receipt
    receipt_data = {
        'receipt_id': f"REC-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'customer_name': customer_name,
        'customer_phone': customer_phone,
        'sale_items': sale_items,
        'total': total_amount
    }
    
    return render_template('receipt.html', receipt=receipt_data)

@app.route('/delete_sale/<sale_id>', methods=['POST'])
@login_required
def delete_sale(sale_id):
    # Find the sale in any sales file
    sale, file_path, sales_data = find_sale_by_id(sale_id)
    
    if not sale:
        flash('Sale not found', 'error')
        return redirect(url_for('sales'))
    
    # Return items to inventory
    return_items_to_inventory(sale)
    
    # Remove the sale from the sales data
    sales_data['sales'] = [s for s in sales_data['sales'] if s['id'] != sale_id]
    
    # Update the daily summary
    sales_data = update_daily_summary(sales_data)
    
    # Save the updated sales data
    with open(file_path, 'w') as f:
        json.dump(sales_data, f, indent=4)
    
    flash('Sale deleted and items returned to inventory', 'success')
    return redirect(url_for('sales'))

@app.route('/expenses')
@login_required
def expenses():
    ensure_folders_exist()
    expenses_data = load_daily_data('expenses')
    return render_template('expenses.html', expenses=expenses_data['expenses'])

@app.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    ensure_folders_exist()
    
    category = request.form['category']
    description = request.form['description']
    amount = float(request.form['amount'])
    
    add_expense_record(category, description, amount)
    
    return redirect(url_for('expenses'))

@app.route('/reports')
@login_required
def reports():
    ensure_folders_exist()
    
    # Get daily summaries
    daily_summaries = get_all_daily_summaries()
    
    # Calculate overall statistics
    total_sales = sum(summary.get('sales_amount', 0) for summary in daily_summaries)
    total_profit = sum(summary.get('profit', 0) for summary in daily_summaries)
    total_expenses = sum(summary.get('expenses', 0) for summary in daily_summaries)
    
    # Get all sales for top items calculation
    all_sales = []
    for filename in os.listdir(SALES_FOLDER):
        if filename.endswith('_sales.json'):
            file_path = os.path.join(SALES_FOLDER, filename)
            with open(file_path, 'r') as f:
                data = json.load(f)
                all_sales.extend(data.get('sales', []))
    
    # Get top selling items
    item_sales = {}
    for sale in all_sales:
        # Skip trade-ins which have negative prices
        if sale.get('type') == 'trade_in':
            continue
        
        item_name = sale['item_name']
        if item_name in item_sales:
            item_sales[item_name]['quantity'] += sale['quantity']
            item_sales[item_name]['revenue'] += sale['total_price']
            item_sales[item_name]['profit'] += sale['profit']
        else:
            item_sales[item_name] = {
                'quantity': sale['quantity'],
                'revenue': sale['total_price'],
                'profit': sale['profit']
            }
    
    top_items = sorted(
        [{'name': name, **stats} for name, stats in item_sales.items()],
        key=lambda x: x['revenue'],
        reverse=True
    )[:10]
    
    return render_template('reports.html',
                           daily_summaries=daily_summaries,
                           total_sales=total_sales,
                           total_profit=total_profit,
                           total_expenses=total_expenses,
                           top_items=top_items)

@app.route('/get_inventory_item/<item_id>', methods=['GET'])
@login_required
def get_inventory_item(item_id):
    inventory_data = load_inventory()
    item = next((item for item in inventory_data['inventory'] if item['id'] == item_id), None)
    
    if item:
        return jsonify(item)
    else:
        return jsonify({'error': 'Item not found'}), 404

@app.route('/add_trade_in', methods=['POST'])
@login_required
def add_trade_in():
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'model_number', 'imei_number', 'trade_in_value']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Return success response with the trade-in data
    return jsonify({'success': True, 'trade_in': data})

@app.route('/add_borrowed_item', methods=['POST'])
@login_required
def add_borrowed_item():
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'category', 'model_number', 'purchase_price', 'selling_price', 'quantity']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Return success response with the borrowed item data
    return jsonify({'success': True, 'borrowed_item': data})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

