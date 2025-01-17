from flask import Flask, render_template,make_response,jsonify,request
from flask_sqlalchemy import SQLAlchemy as SA
from flask_restful import Resource,Api,reqparse
import config 
import mysql.connector
from sqlalchemy import func
import json
from sqlalchemy_serializer import SerializerMixin
from flask_cors import CORS
import json

from sshtunnel import SSHTunnelForwarder

host = '192.168.99.123'
localhost = '127.0.0.1'
ssh_username = 'praveen'
ssh_password = 'password'

# database variables
user='root'
password='password'
database='checking'
server =  SSHTunnelForwarder(
        (host, 22),
        ssh_username = ssh_username,
        ssh_password = password,
        remote_bind_address=(localhost, 3306))

# server.start()

app = Flask('Library Management System')
cors = CORS(app)
app.config["SQLALCHEMY_DATABASE_URI"] = config.DEV
# app.config["SQLALCHEMY_DATABASE_URI"] = 'mysql://root:password@127.0.0.1:{}/LibraryData'.format(server.local_bind_port)

# Flask Mongo connection
from flask_pymongo import PyMongo


db = SA(app)
from utils import result_to_dict

from models import create_models

create_models(db)
from models import Book,Subject,Checkout
parser = reqparse.RequestParser()

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

#Get the first 10 books in the Books Table
@app.route('/lms/api/books', methods=['GET'])
def book():
    def getBooks(parameter):
        books = Book.get_books_10()
        return books
    response = getBooks('bookname')
    
    results = []
    for bucketlist in response:
        obj = {
            'name': bucketlist.title
        }
        results.append(obj)
    response = jsonify(results)
    return response

#Get books based on title. Get suggested books based on the subject of input book title
@app.route('/lms/api/book', methods=['GET'])
def getBookByTitle():
    parser.add_argument('title', type=str)
    args = parser.parse_args()
    
    title = "%" + args['title'].strip() + "%"
    
    book = db.session.execute("SELECT * FROM Book WHERE title LIKE :title",{'title':title})
    book = dict(book.first())
    bibnum = book['bibnum']

    availableCountQuery = db.session.execute("Select ItemCount from Inventory where bibnum=:bibnum  and entrydate = '2018-01-02'",{'bibnum':bibnum})
    checkoutCountQuery = db.session.execute("Select count(*) from Checkout where bibnum=:bibnum and checkoutDay >=01 and checkoutmonth=9 and checkoutyear=2019;",{'bibnum':bibnum})
    
    similairBooks = db.session.execute("select * from SubjectBook join Book on SubjectBook.bibnum = Book.BibNum  where subjectid in (select Subject.subjectid from Subject join SubjectBook on Subject.subjectid = SubjectBook.subjectid where SubjectBook.bibnum = :bibnum)",{'bibnum':bibnum})
    similairBooks = similairBooks.fetchall()
    
    availableCount = availableCountQuery.first()[0]
    checkoutCount = checkoutCountQuery.first()[0]


    if (availableCount - checkoutCount) > 0:
        book['count'] = availableCount - checkoutCount
    else:
        book['count'] = 0


    data = result_to_dict(similairBooks)
    if data:
        del data[0]       #delete the first row from list i.e. searched book title
    return {'book':book,'suggestions': data}

#For a given author, the most popular format for their publications will be displayed 
#which could contribute as a suggestion for their future publications
@app.route('/lms/api/compareCheckoutsByPublishedType', methods=['GET'])
def getCheckoutByItemType():
    parser.add_argument('authorname', type=str)
    args = parser.parse_args()
    
    author = "%" + args['authorname'].strip() + "%"
    
    query = db.session.execute("select AuthorName,Checkout.bibnum,itemtype,count(*) as count from Book,Checkout where Book.bibnum = Checkout.bibnum and AuthorName like :author group by AuthorName,Checkout.bibnum,itemtype order by count desc LIMIT 1;",{'author':author})
    result = result_to_dict(query.fetchall())
    
    return {'response': result}

#Top books to be retired from library which have no check out activity
@app.route('/lms/api/retireBooks', methods=['GET'])
def findBooksToRetire():
    query = db.session.execute("SELECT distinct i.bibnum,b.title, i.itemcount FROM Inventory i left outer join Checkout c on i.bibnum = c.bibnum inner join Book b on i.bibnum=b.bibnum where  i.entrydate = '2018-01-02' and i.ItemCount > 50 and c.checkoutid is NULL order by i.itemcount desc")
    result = result_to_dict(query.fetchall())
    
    return {'response': result}

#Based on most checked out books, list of books to be purchase
@app.route('/lms/api/purchaseBooks', methods=['GET'])
def findBooksToPurchase():
    query = db.session.execute("select c.bibnum,b.title,count(c.bibnum) as count FROM Checkout c inner join Book b on c.bibnum=b.bibnum where checkoutyear=2019 and checkoutmonth=9 and checkoutday=30 group by c.bibnum,b.title order by count desc LIMIT 10")
    result = result_to_dict(query.fetchall())
    
    return {'response': result}



#Session Query to check
@app.route('/lms/api/checkservice', methods=['GET'])
def checkserviceworking():
    subjectsquery = db.session.execute("Select Book.bibnum,Subject.subjectname from Book JOIN SubjectBook JOIN Subject where Book.bibnum = SubjectBook.bibnum and SubjectBook.subjectid = Subject.subjectid group by Book.bibnum,Subject.subjectname order by Book.bibnum;")
    subjectsresult = result_to_dict(subjectsquery.fetchall())

    hashmap = {}
    i = 0
    for rowEle in subjectsresult:
        key = rowEle['bibnum']
        value = rowEle['subjectname']

        if key not in hashmap:
            hashmap[key] = []
            hashmap[key].append(value)
        else:
            hashmap[key].append(value)
        i += 1

    key = value = None

    result = db.session.query(Book).all()
    non_students_dicts = (student.make_dict() for student in result)
    
    i = 0
    responseArray = []
    for row in non_students_dicts:
        if row['bibnum'] in hashmap:
            row['subjectslist'] = hashmap[row['bibnum']]
        responseArray.append(row)
        i += 1
        
    jsonStr = json.dumps(responseArray)
    with open('OutputData/FinalAggregrate.json', 'w') as outfile:
        json.dump(responseArray, outfile)
    return {'response': json.dumps(responseArray)}

@app.route('/lms/api/subjectList', methods=['GET'])
def makeSubjectsArray():
    query = db.session.execute("Select Book.bibnum,Subject.subjectname from Book JOIN SubjectBook JOIN Subject where Book.bibnum = SubjectBook.bibnum and SubjectBook.subjectid = Subject.subjectid group by Book.bibnum,Subject.subjectname order by Book.bibnum;")
    result = result_to_dict(query.fetchall())

    hashmap = {}
    i = 0
    for row in result:
        key = row['bibnum']
        value = row['subjectname']

        if key not in hashmap:
            hashmap[key] = []
            hashmap[key].append(value)
        else:
            hashmap[key].append(value)
        i += 1
        if i > 1000:
            break
    
    with open('Sampledata/SubjectList.json', 'w') as outfile:
        json.dump(hashmap, outfile)
    return {'response': json.dumps(hashmap)}