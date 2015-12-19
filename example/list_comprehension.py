
numbers = [1, 2, 3, 4, 5]
matrix = [[1, 2],[3, 4]]

doubled_odds = []
doubled_numbers = []
flattened = []

def normal_loop_conditional():
    for n in numbers:
        if n % 2 == 1:
            doubled_odds.append(n * 2)

def comprehension_loop_conditional():
    doubled_odds = [n * 2 for n in numbers if n % 2 == 1]

def normal_loop():
    for n in numbers:
        doubled_numbers.append(n * 2)

def comprehension_loop():
    doubled_numbers = [n * 2 for n in numbers]

def normal_nested_loop():
    for row in matrix:
        for n in row:
            flattened.append(n)

def comprehension_nested_loop():
    flattened = [n for row in matrix for n in row]


if __name__ == '__main__':
    normal_loop_conditional()
    comprehension_loop_conditional()
