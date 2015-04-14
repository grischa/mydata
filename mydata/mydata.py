import sys


def main(argv):
    app = MyData("MyData")
    app.MainLoop()

if __name__ == "__main__":
    if sys.argv[1] == 'console':
        from mydata_console import MyData
    else:
        from mydata_gui import MyData
    main(sys.argv)
