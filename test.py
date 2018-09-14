import inspect

def main():
    x, f = 3, lambda a: a + 1
    print(inspect.getsource(f))
    print(dir(f.__code__))

if __name__ == "__main__":
    main()
