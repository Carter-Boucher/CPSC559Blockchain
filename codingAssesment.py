import requests
from bs4 import BeautifulSoup

def parse_google_doc_table(doc_url):
    response = requests.get(doc_url) #GET request to fetch all data
    soup = BeautifulSoup(response.text, 'html.parser') #HTML parser to clean the data
    table = soup.find('table')
    rows = table.find_all('tr')

    table_data = []
    #X at 0, Y at 2, character at 1
    for row in rows:
        cols = row.find_all('td')
        x_coord = cols[0].text.strip()
        y_coord = cols[2].text.strip()
        character = cols[1].text.strip()
        table_data.append((x_coord, y_coord, character))
    table_data.pop(0) #remove header row
    # for i in range(len(table_data)):
    #     print(table_data[i])
    return table_data

def print_data(data):
    coords_dict = {}
    max_x, max_y = 0, 0
    #determine max x and y coordinates to set grid
    for row in data:
        x_str, y_str, char = row
        x, y = int(x_str), int(y_str)
        coords_dict[(x, y)] = char
        if x > max_x:
            max_x = x
        if y > max_y:
            max_y = y
    #print the grid reversed so 0,0 is at the bottom left
    for y in reversed(range(max_y + 1)):
        row_chars = []
        for x in range(max_x + 1):
            row_chars.append(coords_dict.get((x, y), ' '))
        print("".join(row_chars))

if __name__ == "__main__":
    doc_url = input("Enter the Google Doc URL: ").strip() #prompt for user input
    table_data = parse_google_doc_table(doc_url) #parse and clean table data
    print_data(table_data) #print decoded message