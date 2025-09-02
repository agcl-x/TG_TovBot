# 🛍️ Telegram Shop Bot

A multifunctional Telegram bot for managing orders, connected to an SQLite database.  
It allows customers to place orders, check their previous purchases, and contact a manager.  
Admins can manage orders, track statuses, and automate posting products to a channel.

---

## ⚙️ Features

### 🔹 For Users
- `/start` — start the bot and see the main menu.
- 🛍️ **Make an Order** — choose products by article number or forward a product message.
- 🛒 **My Orders** — view your past orders with full details.
- ✉ **Contact Manager** — send a message to the admin directly.

### 🔹 For Admins
- `/orderlist` — view all orders, check details, and update tracking numbers (TTN).
- `/start_sending` — start automatic scheduled posting of products to the channel.
- `/stop_sending` — stop scheduled posting.
- `/recheckstatus` — recheck product statuses in the database.
- Detailed notifications for each new order.

### 🔹 Extra
- ✅ User-friendly order flow (step-by-step collection of name, phone, address).
- 📦 Tracks product sizes, availability, and updates stock automatically after each order.
- 🖼️ Sends product messages with images and formatted description to the channel.
- 📑 Each user and order is logged in a dedicated file (`logs/`).

---

## 📂 Project Structure

